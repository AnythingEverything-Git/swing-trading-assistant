"""Groww-style research endpoints for stock detail tabs."""
from __future__ import annotations

import json
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_db, get_query_service, get_upstox_provider
from app.api.schemas import (
    CorporateActionItemResponse,
    FnoResearchResponse,
    FaProxyMetricResponse,
    IndicatorReadingResponse,
    InsightSectionResponse,
    NewsEventsResearchResponse,
    NewsItemResponse,
    OptionChainRowResponse,
    OverviewResearchResponse,
    PerformancePointResponse,
    PivotLevelsResponse,
    PlanDeductionRephraseRequest,
    PlanDeductionRephraseResponse,
    PlanDeductionStepPayload,
    QualityCheckResponse,
    ResearchInsightRequest,
    ResearchInsightResponse,
    SimilarSetupItemResponse,
    SimilarSetupsResponse,
    TechnicalResearchResponse,
)
from app.application.market_data.query_service import MarketDataQueryService
from app.application.narrative.deduction_rephraser import DeductionRephraser, normalize_steps
from app.application.narrative.gemini_narrator import GeminiNarrator
from app.application.narrative.insight_cache import (
    get_cached_insight,
    insight_cache_key,
    put_cached_insight,
)
from app.application.research.overview_service import build_overview_snapshot
from app.application.research.technical_service import build_technical_snapshot
from app.core.config import get_settings
from app.infrastructure.news.nse_news_provider import NseNewsProvider

router = APIRouter(prefix="/api/v1/research", tags=["research"])

_UNIVERSE_DATA = Path(__file__).resolve().parents[2] / "infrastructure" / "universe" / "data"

_COARSE_SECTOR_LABEL = {
    "BANKING": "Banking",
    "IT": "IT",
    "ENERGY": "Energy",
    "AUTO": "Auto",
    "PHARMA": "Pharma",
    "FMCG": "FMCG",
    "METALS": "Metals",
}


@lru_cache(maxsize=1)
def _sector_payload() -> tuple[dict[str, str], dict[str, str]]:
    path = _UNIVERSE_DATA / "nse_sector_map.json"
    if not path.exists():
        return {}, {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}, {}
    sectors_raw = raw.get("sectors") if isinstance(raw.get("sectors"), dict) else {}
    industries_raw = raw.get("industries") if isinstance(raw.get("industries"), dict) else {}
    sectors = {str(k).upper(): str(v) for k, v in sectors_raw.items()}
    industries = {str(k).upper(): str(v) for k, v in industries_raw.items()}
    return sectors, industries


def _sector_label(symbol: str) -> str | None:
    """Human-readable sector for FA Snapshot (industry preferred)."""
    sectors, industries = _sector_payload()
    sym = symbol.upper()
    industry = (industries.get(sym) or "").strip()
    coarse = (sectors.get(sym) or "").strip().upper()
    if industry:
        if coarse and coarse != "UNKNOWN":
            bucket = _COARSE_SECTOR_LABEL.get(coarse, coarse.title())
            return f"{bucket} - {industry}"
        return industry
    if coarse and coarse != "UNKNOWN":
        return _COARSE_SECTOR_LABEL.get(coarse, coarse.title())
    return None


@lru_cache(maxsize=1)
def _surveillance_entries() -> list[dict]:
    path = _UNIVERSE_DATA / "surveillance_blocked.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("entries") if isinstance(raw, dict) else None
    return list(entries or [])


@lru_cache(maxsize=1)
def _corporate_action_entries() -> list[dict]:
    path = _UNIVERSE_DATA / "corporate_actions.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("entries") if isinstance(raw, dict) else None
    return list(entries or [])


def _caution_flags_for(symbol: str, as_of: date | None = None) -> list[str]:
    sym = symbol.upper()
    today = as_of or datetime.now(timezone.utc).date()
    flags: list[str] = []
    for entry in _surveillance_entries():
        if str(entry.get("symbol", "")).upper() != sym:
            continue
        start = entry.get("from")
        end = entry.get("to")
        try:
            start_d = date.fromisoformat(str(start)[:10]) if start else None
            end_d = date.fromisoformat(str(end)[:10]) if end else None
        except ValueError:
            continue
        if start_d and today < start_d:
            continue
        if end_d and today > end_d:
            continue
        reason = str(entry.get("reason") or "SURVEILLANCE").replace("_", " ")
        flags.append(f"Surveillance: {reason}")
    for entry in _corporate_action_entries():
        if str(entry.get("symbol", "")).upper() != sym:
            continue
        try:
            ex = date.fromisoformat(str(entry.get("ex_date", ""))[:10])
        except ValueError:
            continue
        days = (ex - today).days
        ca_type = str(entry.get("type") or "CA")
        # Near-term CA awareness (±7) and upcoming CA within 30 days.
        if abs(days) <= 7:
            flags.append(f"Near CA: {ca_type} ex {ex.isoformat()}")
        elif 0 < days <= 30:
            flags.append(f"CA in {days} days: {ca_type} ex {ex.isoformat()}")
    return flags


def _quality_checks_for(
    *,
    sector: str | None,
    candle_count: int,
    caution_flags: list[str],
) -> list[QualityCheckResponse]:
    """Three fixed FA quality checks — always labeled so the UI is never ambiguous."""
    surv_hits = [f for f in caution_flags if f.lower().startswith("surveillance")]
    ca_hits = [f for f in caution_flags if "ca" in f.lower()]

    if surv_hits:
        surv = QualityCheckResponse(
            id="surveillance",
            label="Surveillance",
            status="warn",
            detail=surv_hits[0].replace("Surveillance: ", "", 1),
        )
    else:
        surv = QualityCheckResponse(
            id="surveillance",
            label="Surveillance",
            status="clear",
            detail="Not on ASM / GSM watch lists",
        )

    if ca_hits:
        ca = QualityCheckResponse(
            id="corporate_action",
            label="Corporate action",
            status="warn",
            detail=ca_hits[0],
        )
    else:
        ca = QualityCheckResponse(
            id="corporate_action",
            label="Corporate action",
            status="clear",
            detail="No ex-date within the next 30 days",
        )

    coverage_issues: list[str] = []
    if not sector:
        coverage_issues.append("sector unclassified")
    if candle_count < 120:
        coverage_issues.append(f"thin history ({candle_count} bars)")
    if coverage_issues:
        data = QualityCheckResponse(
            id="data_coverage",
            label="Data coverage",
            status="warn",
            detail="; ".join(coverage_issues).capitalize(),
        )
    else:
        data = QualityCheckResponse(
            id="data_coverage",
            label="Data coverage",
            status="clear",
            detail=f"{candle_count} daily bars | sector mapped",
        )

    return [surv, ca, data]


def _quality_flags_for(
    *,
    symbol: str,
    sector: str | None,
    candle_count: int,
    caution_flags: list[str],
) -> list[str]:
    """Legacy string list derived from structured checks (warn only)."""
    return [
        f"{c.label}: {c.detail}"
        for c in _quality_checks_for(
            sector=sector,
            candle_count=candle_count,
            caution_flags=caution_flags,
        )
        if c.status == "warn"
    ]


def _caution_summary(caution_flags: list[str]) -> str:
    if not caution_flags:
        return "No near-term caution"
    first = caution_flags[0]
    if first.lower().startswith("ca in "):
        return f"Caution: {first}"
    if first.lower().startswith("near ca"):
        return f"Caution: {first}"
    return f"Caution: {first}"


def _fa_proxies(
    *,
    performance: list,
    last_close: Decimal | None,
    high_52w: Decimal | None,
    low_52w: Decimal | None,
    last_volume: int | None,
    range_pct: Decimal | None,
    accounting: dict[str, Decimal | None] | None = None,
) -> list[FaProxyMetricResponse]:
    by_label = {p.label: p.change_percent for p in performance}
    period_note = {
        "1M": "Share-price move over the last month - not company revenue growth.",
        "3M": "Share-price move over the last quarter - a momentum cue only.",
        "1Y": "Share-price move over the last year - useful context, not fundamentals.",
    }
    proxies: list[FaProxyMetricResponse] = []
    acct = accounting or {}

    rev = acct.get("revenue_growth_pct")
    margin = acct.get("profit_margin_pct")
    roe = acct.get("roe_pct")
    proxies.append(
        FaProxyMetricResponse(
            label="Revenue growth",
            value=None if rev is None else f"{rev}%",
            change_percent=rev,
            available=rev is not None,
            note=(
                "YoY change in reported revenue (latest two fiscal years)."
                if rev is not None
                else "Reported revenue growth unavailable for this symbol."
            ),
        )
    )
    proxies.append(
        FaProxyMetricResponse(
            label="Margin",
            value=None if margin is None else f"{margin}%",
            change_percent=None,
            available=margin is not None,
            note=(
                "Latest fiscal net profit as a % of revenue."
                if margin is not None
                else "Reported profit margin unavailable for this symbol."
            ),
        )
    )
    proxies.append(
        FaProxyMetricResponse(
            label="ROE",
            value=None if roe is None else f"{roe}%",
            change_percent=None,
            available=roe is not None,
            note=(
                "Return on equity from published ratios."
                if roe is not None
                else "ROE unavailable for this symbol."
            ),
        )
    )

    for label in ("1M", "3M", "1Y"):
        pct = by_label.get(label)
        proxies.append(
            FaProxyMetricResponse(
                label=f"{label} return",
                value=None if pct is None else f"{pct}%",
                change_percent=pct,
                available=pct is not None,
                note=period_note[label],
            )
        )
    proxies.append(
        FaProxyMetricResponse(
            label="52W position",
            value=None if range_pct is None else f"{range_pct}%",
            change_percent=None,
            available=range_pct is not None,
            note="0% = at the 52-week low; 100% = at the 52-week high.",
        )
    )
    proxies.append(
        FaProxyMetricResponse(
            label="Last volume",
            value=None if last_volume is None else f"{last_volume:,}",
            available=last_volume is not None,
            note="Shares traded in the latest session - a quick liquidity check.",
        )
    )
    return proxies


async def _accounting_metrics(symbol: str) -> dict[str, Decimal | None]:
    """Best-effort FA ratios via Tickertape public JSON (NSE)."""
    out: dict[str, Decimal | None] = {
        "revenue_growth_pct": None,
        "profit_margin_pct": None,
        "roe_pct": None,
    }
    headers = {
        "User-Agent": "TradePilot/1.0",
        "Accept": "application/json",
        "Referer": "https://www.tickertape.in/",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            search = await client.get(
                "https://api.tickertape.in/search",
                params={"text": symbol.upper(), "types": "stock"},
            )
            if search.status_code != 200:
                return out
            payload = search.json()
            stocks = ((payload.get("data") or {}).get("stocks") or [])
            sid = None
            for row in stocks:
                if str(row.get("ticker", "")).upper() == symbol.upper():
                    sid = row.get("sid")
                    break
            if not sid and stocks:
                sid = stocks[0].get("sid")
            if not sid:
                return out

            info_res, summary_res = await asyncio.gather(
                client.get(f"https://api.tickertape.in/stocks/info/{sid}"),
                client.get(f"https://api.tickertape.in/stocks/summary/{sid}"),
            )
            if info_res.status_code == 200:
                ratios = ((info_res.json().get("data") or {}).get("ratios") or {})
                roe = ratios.get("roe")
                if roe is not None:
                    out["roe_pct"] = Decimal(str(roe)).quantize(Decimal("0.01"))

            if summary_res.status_code == 200:
                years = (
                    ((summary_res.json().get("data") or {}).get("financialSummary") or {}).get(
                        "fiscalYearToData"
                    )
                    or []
                )
                rows = [
                    y
                    for y in years
                    if y.get("revenue") is not None and y.get("profit") is not None
                ]
                if rows:
                    latest = rows[-1]
                    rev = Decimal(str(latest["revenue"]))
                    profit = Decimal(str(latest["profit"]))
                    if rev != 0:
                        out["profit_margin_pct"] = ((profit / rev) * Decimal("100")).quantize(
                            Decimal("0.01")
                        )
                if len(rows) >= 2:
                    prev_rev = Decimal(str(rows[-2]["revenue"]))
                    curr_rev = Decimal(str(rows[-1]["revenue"]))
                    if prev_rev != 0:
                        out["revenue_growth_pct"] = (
                            ((curr_rev - prev_rev) / prev_rev) * Decimal("100")
                        ).quantize(Decimal("0.01"))
    except Exception:
        return out
    return out


def _default_range(end: datetime | None, start: datetime | None) -> tuple[datetime, datetime]:
    resolved_end = end or datetime.now(timezone.utc)
    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)
    resolved_start = start or (resolved_end - timedelta(days=400))
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=timezone.utc)
    if resolved_start > resolved_end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    return resolved_start, resolved_end


@router.get("/{symbol}/overview", response_model=OverviewResearchResponse)
async def research_overview(
    symbol: str,
    request: Request,
    timeframe: str = Query("1d"),
    start: datetime | None = None,
    end: datetime | None = None,
    svc: MarketDataQueryService = Depends(get_query_service),
) -> OverviewResearchResponse:
    resolved_start, resolved_end = _default_range(end, start)
    candles = await svc.get_candles(symbol.upper(), timeframe, resolved_start, resolved_end)
    snapshot = build_overview_snapshot(symbol.upper(), timeframe, candles)

    current_price = snapshot.last_close
    change_pct = None
    if len(candles) >= 2 and candles[-2].close and candles[-2].close != 0 and snapshot.last_close is not None:
        change_pct = ((snapshot.last_close - candles[-2].close) / candles[-2].close) * Decimal("100")

    provider = getattr(request.app.state, "ingest_provider", None) or getattr(
        request.app.state, "upstox_provider", None
    )
    # Live Upstox LTP overlays persisted close; demo synthetic quotes must not diverge from the chart.
    from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider

    quote_fn = getattr(provider, "get_last_traded_prices", None)
    if quote_fn is not None and not isinstance(provider, DemoMarketDataProvider):
        try:
            quotes = await quote_fn([symbol.upper()])
            payload = quotes.get(symbol.upper())
            if payload:
                current_price = payload.get("last_price") or current_price
                raw = payload.get("raw") or {}
                net_change = raw.get("net_change")
                if net_change is not None and current_price:
                    net = Decimal(str(net_change))
                    prev = current_price - net
                    if prev != 0:
                        change_pct = (net / prev) * Decimal("100")
        except Exception:
            pass

    sector = _sector_label(snapshot.symbol)
    caution_flags = _caution_flags_for(snapshot.symbol)
    quality_checks = _quality_checks_for(
        sector=sector,
        candle_count=snapshot.candle_count,
        caution_flags=caution_flags,
    )
    quality_flags = [f"{c.label}: {c.detail}" for c in quality_checks if c.status == "warn"]
    range_pct = None
    if (
        snapshot.last_close is not None
        and snapshot.high_52w is not None
        and snapshot.low_52w is not None
        and snapshot.high_52w != snapshot.low_52w
    ):
        range_pct = (
            (snapshot.last_close - snapshot.low_52w) / (snapshot.high_52w - snapshot.low_52w) * Decimal("100")
        ).quantize(Decimal("0.1"))

    performance = [
        PerformancePointResponse(label=p.label, change_percent=p.change_percent)
        for p in snapshot.performance
    ]
    accounting = await _accounting_metrics(snapshot.symbol)
    return OverviewResearchResponse(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        last_close=snapshot.last_close,
        last_volume=snapshot.last_volume,
        performance=performance,
        high_52w=snapshot.high_52w,
        low_52w=snapshot.low_52w,
        candle_count=snapshot.candle_count,
        current_price=current_price,
        current_price_change_percent=change_pct,
        sector=sector,
        caution_flags=caution_flags,
        quality_flags=quality_flags,
        quality_checks=quality_checks,
        caution_summary=_caution_summary(caution_flags),
        range_52w_position_pct=range_pct,
        fa_proxies=_fa_proxies(
            performance=performance,
            last_close=snapshot.last_close,
            high_52w=snapshot.high_52w,
            low_52w=snapshot.low_52w,
            last_volume=snapshot.last_volume,
            range_pct=range_pct,
            accounting=accounting,
        ),
    )


@router.get("/{symbol}/technical", response_model=TechnicalResearchResponse)
async def research_technical(
    symbol: str,
    timeframe: str = Query("1d"),
    start: datetime | None = None,
    end: datetime | None = None,
    svc: MarketDataQueryService = Depends(get_query_service),
) -> TechnicalResearchResponse:
    resolved_start, resolved_end = _default_range(end, start)
    candles = await svc.get_candles(symbol.upper(), timeframe, resolved_start, resolved_end)
    snapshot = build_technical_snapshot(symbol.upper(), timeframe, candles)
    pivots = None
    if snapshot.pivots is not None:
        pivots = PivotLevelsResponse(
            pivot=snapshot.pivots.pivot,
            resistance_1=snapshot.pivots.resistance_1,
            resistance_2=snapshot.pivots.resistance_2,
            resistance_3=snapshot.pivots.resistance_3,
            support_1=snapshot.pivots.support_1,
            support_2=snapshot.pivots.support_2,
            support_3=snapshot.pivots.support_3,
        )

    orb_snapshot = None
    orb_high = None
    orb_low = None
    orb_armed = False
    orb_status = "unavailable"
    try:
        from datetime import time as dt_time

        from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1
        from app.domain.intraday.eligibility import eligibility_flags
        from app.domain.intraday.opening_range import build_opening_range
        from app.domain.intraday.session_calendar import IST, combine_ist

        session_date = datetime.now(IST).date()
        or_start = combine_ist(session_date, dt_time(9, 15))
        or_end = combine_ist(session_date, dt_time(15, 30))
        candles_1m = await svc.get_candles(symbol.upper(), "1m", or_start, or_end)
        orng = build_opening_range(symbol.upper(), session_date, candles_1m, DEFAULT_CONFIG_V1)
        flags = eligibility_flags(symbol.upper(), session_date)
        blocked = bool(flags.get("surveillance_blocked") or flags.get("corporate_action_blocked"))
        if orng is not None:
            orb_high = orng.high
            orb_low = orng.low
            orb_snapshot = ((orng.high + orng.low) / Decimal("2")).quantize(Decimal("0.01"))
            orb_armed = not blocked
            orb_status = "armed" if orb_armed else "blocked"
        elif candles_1m:
            orb_status = "building" if not blocked else "blocked"
        else:
            orb_status = "no_1m_data"
    except Exception:
        orb_status = "unavailable"

    # Prefer confirmed strategy evaluate eligibility when caller already loaded it in UI;
    # panel still shows indicator consensus from snapshot.
    swing_eligible = snapshot.swing_eligible

    return TechnicalResearchResponse(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        last_close=snapshot.last_close,
        indicators=[
            IndicatorReadingResponse(
                name=item.name,
                value=item.value,
                signal=item.signal,
                detail=item.detail,
            )
            for item in snapshot.indicators
        ],
        pivots=pivots,
        volume_vs_sma=snapshot.volume_vs_sma,
        support=snapshot.support,
        resistance=snapshot.resistance,
        trendline=snapshot.trendline,
        atr=snapshot.atr,
        swing_fit=snapshot.swing_fit,
        swing_eligible=swing_eligible,
        orb_snapshot=orb_snapshot,
        orb_high=orb_high,
        orb_low=orb_low,
        orb_armed=orb_armed,
        orb_status=orb_status,
    )


@router.get("/{symbol}/fno", response_model=FnoResearchResponse)
async def research_fno(
    symbol: str,
    expiry: str = Query("current_month"),
    provider=Depends(get_upstox_provider),
    svc: MarketDataQueryService = Depends(get_query_service),
) -> FnoResearchResponse:
    from datetime import timedelta, timezone

    from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider

    chain_fn = getattr(provider, "get_option_chain", None)
    if chain_fn is None:
        return FnoResearchResponse(
            symbol=symbol.upper(),
            expiry_date=expiry,
            status="unavailable",
            detail="When F&O data unavailable show Unavailable",
            futures_premium_status="unavailable",
            oi_change_status="unavailable",
        )
    try:
        payload = await chain_fn(symbol.upper(), expiry)
    except Exception as exc:
        return FnoResearchResponse(
            symbol=symbol.upper(),
            expiry_date=expiry,
            status="unavailable",
            detail=str(exc) or "When F&O data unavailable show Unavailable",
            futures_premium_status="unavailable",
            oi_change_status="unavailable",
        )

    # Align demo chain spot with the same persisted last close the chart uses.
    if isinstance(provider, DemoMarketDataProvider):
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=21)
            candles = await svc.get_candles(symbol.upper(), "1d", start, end)
            if candles:
                spot_db = candles[-1].close
                payload["spot"] = spot_db
                payload["futures_ltp"] = spot_db + Decimal("0.5")
                payload["futures_premium"] = Decimal("0.5")
                payload["futures_premium_status"] = "ok"
        except Exception:
            pass

    rows_raw = list(payload.get("rows") or [])
    rows = [OptionChainRowResponse(**row) for row in rows_raw]

    call_wall_strike: Decimal | None = None
    put_wall_strike: Decimal | None = None
    call_wall_oi: Decimal | None = None
    put_wall_oi: Decimal | None = None
    total_call_oi = Decimal("0")
    total_put_oi = Decimal("0")
    call_oi_change = Decimal("0")
    put_oi_change = Decimal("0")
    call_chg_seen = False
    put_chg_seen = False

    for row in rows:
        c_oi = row.call_oi if row.call_oi is not None else Decimal("0")
        p_oi = row.put_oi if row.put_oi is not None else Decimal("0")
        total_call_oi += c_oi
        total_put_oi += p_oi
        if row.call_oi is not None and (call_wall_oi is None or row.call_oi > call_wall_oi):
            call_wall_oi = row.call_oi
            call_wall_strike = row.strike
        if row.put_oi is not None and (put_wall_oi is None or row.put_oi > put_wall_oi):
            put_wall_oi = row.put_oi
            put_wall_strike = row.strike
        if row.call_oi_change is not None:
            call_oi_change += row.call_oi_change
            call_chg_seen = True
        if row.put_oi_change is not None:
            put_oi_change += row.put_oi_change
            put_chg_seen = True

    pcr = payload.get("pcr")
    if pcr is None and total_call_oi > 0:
        pcr = (total_put_oi / total_call_oi).quantize(Decimal("0.0001"))

    oi_change: Decimal | None = None
    oi_change_status = "unavailable"
    if call_chg_seen or put_chg_seen:
        oi_change = Decimal("0")
        if call_chg_seen:
            oi_change += call_oi_change
        if put_chg_seen:
            oi_change += put_oi_change
        oi_change_status = "ok"

    futures_ltp = payload.get("futures_ltp")
    futures_premium = payload.get("futures_premium")
    futures_premium_status = str(payload.get("futures_premium_status") or "unavailable")
    spot = payload.get("spot")
    if futures_ltp is not None and spot is not None and futures_premium is None:
        try:
            futures_premium = Decimal(str(futures_ltp)) - Decimal(str(spot))
            futures_premium_status = "ok"
        except Exception:
            futures_premium = None
            futures_premium_status = "unavailable"

    return FnoResearchResponse(
        symbol=payload.get("symbol", symbol.upper()),
        expiry_date=payload.get("expiry_date", expiry),
        expiry=payload.get("expiry"),
        spot=spot,
        pcr=pcr,
        futures_ltp=futures_ltp,
        futures_premium=futures_premium,
        futures_premium_status=futures_premium_status,
        oi_change=oi_change,
        call_oi_change=call_oi_change if call_chg_seen else None,
        put_oi_change=put_oi_change if put_chg_seen else None,
        oi_change_status=oi_change_status,
        call_wall_strike=call_wall_strike,
        put_wall_strike=put_wall_strike,
        call_wall_oi=call_wall_oi,
        put_wall_oi=put_wall_oi,
        rows=rows,
        status="ok" if rows else "unavailable",
        detail=None if rows else "When F&O data unavailable show Unavailable",
    )


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _corporate_actions_for_symbol(symbol: str) -> list[CorporateActionItemResponse]:
    sym = symbol.upper()
    items: list[CorporateActionItemResponse] = []
    for entry in _corporate_action_entries():
        if str(entry.get("symbol", "")).upper() != sym:
            continue
        ex = _parse_iso_date(str(entry.get("ex_date") or ""))
        if ex is None:
            continue
        block = max(1, int(entry.get("block_sessions") or 1))
        ca_type = str(entry.get("type") or "CA").upper()
        end = ex + timedelta(days=max(0, block - 1))
        items.append(
            CorporateActionItemResponse(
                symbol=sym,
                ex_date=ex.isoformat(),
                type=ca_type,
                block_sessions=block,
                end_date=end.isoformat(),
                source="local",
                label=ca_type.title().replace("_", " "),
            )
        )
    items.sort(key=lambda row: row.ex_date)
    return items


def _actions_from_news_events(symbol: str, events: list) -> list[CorporateActionItemResponse]:
    """Promote NSE event rows with parseable dates into calendar markers."""
    sym = symbol.upper()
    out: list[CorporateActionItemResponse] = []
    for item in events:
        if isinstance(item, dict):
            published = item.get("published_at")
            title = str(item.get("title") or "")
        else:
            published = getattr(item, "published_at", None)
            title = str(getattr(item, "title", "") or "")
        ex = _parse_iso_date(published)
        if ex is None:
            continue
        upper = title.upper()
        if "DIVIDEND" in upper:
            ca_type = "DIVIDEND"
        elif "SPLIT" in upper:
            ca_type = "SPLIT"
        elif "BONUS" in upper:
            ca_type = "BONUS"
        elif "RIGHT" in upper:
            ca_type = "RIGHTS"
        else:
            ca_type = "EVENT"
        block = 1 if ca_type == "EVENT" else 2
        out.append(
            CorporateActionItemResponse(
                symbol=sym,
                ex_date=ex.isoformat(),
                type=ca_type,
                block_sessions=block,
                end_date=(ex + timedelta(days=max(0, block - 1))).isoformat(),
                source="nse",
                label=ca_type.title() if ca_type != "EVENT" else (title[:28] or "Event"),
            )
        )
    return out


@router.get("/{symbol}/news-events", response_model=NewsEventsResearchResponse)
async def research_news_events(symbol: str) -> NewsEventsResearchResponse:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        snapshot = await NseNewsProvider(client).get_news_events(symbol.upper())

    local_actions = _corporate_actions_for_symbol(snapshot.symbol)
    nse_actions = _actions_from_news_events(snapshot.symbol, list(snapshot.events))
    # Prefer local typed CA; append NSE-derived that don't collide on ex_date+type.
    seen = {(a.ex_date, a.type) for a in local_actions}
    merged = list(local_actions)
    for action in nse_actions:
        key = (action.ex_date, action.type)
        if key in seen:
            continue
        seen.add(key)
        merged.append(action)
    merged.sort(key=lambda row: row.ex_date)

    caution_flags = _caution_flags_for(snapshot.symbol)
    trading_caution = any(
        f.lower().startswith("near ca") or f.lower().startswith("ca in ") or "surveillance" in f.lower()
        for f in caution_flags
    )
    return NewsEventsResearchResponse(
        symbol=snapshot.symbol,
        announcements=[
            NewsItemResponse(
                title=item.title,
                published_at=item.published_at,
                source=item.source,
                category=item.category,
                url=item.url,
            )
            for item in snapshot.announcements
        ],
        events=[
            NewsItemResponse(
                title=item.title,
                published_at=item.published_at,
                source=item.source,
                category=item.category,
                url=item.url,
            )
            for item in snapshot.events
        ],
        corporate_actions=merged,
        trading_caution=trading_caution or bool(caution_flags),
        caution_summary=_caution_summary(caution_flags),
        status=snapshot.status,
        detail=snapshot.detail,
    )


@router.post("/{symbol}/insight", response_model=ResearchInsightResponse)
async def research_insight(
    symbol: str,
    payload: ResearchInsightRequest,
) -> ResearchInsightResponse:
    context = dict(payload.context or {})
    context.setdefault("symbol", symbol.upper())
    tab = (payload.tab or "overview").strip().lower()
    if tab not in {"overview", "technical", "news", "setup", "fno"}:
        raise HTTPException(status_code=400, detail="tab must be overview|technical|news|setup|fno")

    cache_key = insight_cache_key(symbol, tab, context)
    cached = get_cached_insight(cache_key)
    if cached is not None:
        return ResearchInsightResponse(
            title=cached.title,
            headline=cached.headline,
            bullets=list(cached.bullets),
            sections=[InsightSectionResponse(label=s.label, text=s.text) for s in cached.sections],
            provider=cached.provider,
            grounded=cached.grounded,
            detail=cached.detail,
            cached=True,
        )

    async with httpx.AsyncClient() as client:
        result = await GeminiNarrator(client, get_settings()).generate_insight(tab=tab, context=context)
    put_cached_insight(cache_key, result)
    return ResearchInsightResponse(
        title=result.title,
        headline=result.headline,
        bullets=list(result.bullets),
        sections=[InsightSectionResponse(label=s.label, text=s.text) for s in result.sections],
        provider=result.provider,
        grounded=result.grounded,
        detail=result.detail,
        cached=False,
    )


@router.post("/plan-deduction/rephrase", response_model=PlanDeductionRephraseResponse)
async def rephrase_plan_deduction(
    payload: PlanDeductionRephraseRequest,
) -> PlanDeductionRephraseResponse:
    """Polish beginner wording only. Numbers and strategy facts stay locked to the request."""
    source = normalize_steps([step.model_dump() for step in payload.steps])
    if not source:
        raise HTTPException(status_code=400, detail="steps required")

    async with httpx.AsyncClient() as client:
        result = await DeductionRephraser(client, get_settings()).rephrase(
            symbol=payload.symbol,
            steps=source,
        )

    return PlanDeductionRephraseResponse(
        symbol=payload.symbol.upper().strip(),
        steps=[
            PlanDeductionStepPayload(
                id=step.id,
                title=step.title,
                value=step.value,
                summary=step.summary,
                details=list(step.details),
            )
            for step in result.steps
        ],
        provider=result.provider,
        grounded=result.grounded,
        detail=result.detail,
    )


@router.get("/{symbol}/similar-setups", response_model=SimilarSetupsResponse)
async def similar_setups(
    symbol: str,
    direction: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    forward_bars: int = Query(default=10, ge=3, le=30),
    session=Depends(get_db),
    query: MarketDataQueryService = Depends(get_query_service),
) -> SimilarSetupsResponse:
    """Deterministic similar-setup retrieval from historical ScanRuns + candle forward path."""
    from app.application.narrative.grounded_narrator import GroundedNarrator, narrative_llm_enabled
    from app.application.research.similar_setups import (
        fingerprint_from_opportunity_payload,
        fingerprint_from_strategy_result,
        forward_outcome_from_candles,
        rank_similar,
        similar_blurb,
    )
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy
    from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
    from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository

    symbol_u = symbol.upper().strip()
    runs = await ScanRunRepository(session).list_recent(limit=40)
    corpus: list[SetupFingerprint] = []
    query_fp: SetupFingerprint | None = None
    query_source: str | None = None

    for run in runs:
        payload = run.result_payload or {}
        items = list(payload.get("opportunities") or [])
        if not items:
            items = list(payload.get("top") or [])
        for item in items:
            fp = fingerprint_from_opportunity_payload(item, scan_run_id=run.id)
            if fp is None:
                continue
            corpus.append(fp)
            if fp.symbol == symbol_u and (direction is None or fp.direction == direction.upper()):
                if query_fp is None or fp.confirmation_time > query_fp.confirmation_time:
                    query_fp = fp
                    query_source = "scan"

    if query_fp is None:
        # Live evaluate fallback so Similar works without the symbol appearing in scan history.
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=400)
        try:
            eval_svc = StrategyEvaluationService(query, BreakoutRetestConfirmationStrategy())
            result = await eval_svc.evaluate(symbol_u, "1d", start, end)
        except Exception:
            result = None
        if result is not None and result.has_setup and result.candidate is not None and result.evidence is not None:
            conf = result.evidence.confirmation_candle_time or end
            if direction is None or str(result.candidate.direction).upper() == direction.upper():
                entry = Decimal(str(result.candidate.entry_price))
                stop = Decimal(str(result.candidate.stop_loss))
                risk_pct = Decimal("0")
                if entry:
                    risk_pct = (abs(entry - stop) / entry * Decimal("100")).quantize(Decimal("0.01"))
                query_fp = fingerprint_from_strategy_result(
                    symbol_u,
                    direction=str(result.candidate.direction),
                    confirmation_time=conf if isinstance(conf, datetime) else end,
                    entry=entry,
                    stop=stop,
                    target=Decimal(str(result.candidate.target)),
                    risk_reward_ratio=Decimal(str(result.candidate.risk_reward_ratio or "0")),
                    atr_value=Decimal(str(result.evidence.atr_value or "0")),
                    setup_name=str(result.candidate.setup_name or "BreakoutRetest"),
                    risk_percent=risk_pct,
                )
                query_source = "evaluate"

    if query_fp is None:
        return SimilarSetupsResponse(
            symbol=symbol_u,
            direction=direction,
            matches=[],
            provider="template",
            query_source=None,
            setup_family=None,
            detail="No confirmed setup for this symbol yet - run Evaluate or Find Setups to build peers.",
        )

    if not corpus:
        return SimilarSetupsResponse(
            symbol=symbol_u,
            direction=query_fp.direction,
            matches=[],
            provider="template",
            query_source=query_source,
            setup_family=query_fp.setup_name,
            detail="No scan history peers yet - run Find Setups to populate similar setups.",
        )

    neighbors = rank_similar(query_fp, corpus, limit=limit)
    settings = get_settings()
    matches: list[SimilarSetupItemResponse] = []
    narrator = None
    client = None
    if narrative_llm_enabled(settings):
        client = httpx.AsyncClient(timeout=20.0)
        narrator = GroundedNarrator(client, settings)
    try:
        for peer, distance in neighbors:
            start = peer.confirmation_time - timedelta(days=5)
            end = max(
                peer.confirmation_time + timedelta(days=max(forward_bars * 3, 40)),
                datetime.now(timezone.utc),
            )
            try:
                candles = await query.get_candles(peer.symbol, "1d", start, end)
            except Exception:
                candles = []
            ret, hit_t, hit_s = forward_outcome_from_candles(
                candles,
                confirmation_time=peer.confirmation_time,
                direction=peer.direction,
                entry=peer.entry,
                stop=peer.stop,
                target=peer.target,
                forward_bars=forward_bars,
            )
            measured_bars = forward_bars
            if ret is None and candles:
                ret, hit_t, hit_s = forward_outcome_from_candles(
                    candles,
                    confirmation_time=peer.confirmation_time,
                    direction=peer.direction,
                    entry=peer.entry,
                    stop=peer.stop,
                    target=peer.target,
                    forward_bars=max(1, min(forward_bars, len(candles))),
                )
                if ret is not None:
                    measured_bars = max(1, min(forward_bars, len(candles) - 1))
            blurb = await similar_blurb(
                narrator,
                match=peer,
                forward_return_pct=ret,
                forward_bars=measured_bars,
            )
            matches.append(
                SimilarSetupItemResponse(
                    symbol=peer.symbol,
                    direction=peer.direction,
                    confirmation_time=peer.confirmation_time,
                    quality_score=peer.quality_score,
                    atr_percent=peer.atr_percent,
                    risk_reward_ratio=peer.risk_reward_ratio,
                    distance=distance,
                    forward_bars=measured_bars,
                    forward_return_pct=ret,
                    hit_target=hit_t,
                    hit_stop=hit_s,
                    blurb=blurb.text,
                    blurb_provider=blurb.provider,
                    scan_run_id=peer.scan_run_id,
                    entry_price=peer.entry,
                    stop_loss=peer.stop,
                    target=peer.target,
                    setup_name=peer.setup_name or "BreakoutRetest",
                )
            )
    finally:
        if client is not None:
            await client.aclose()

    return SimilarSetupsResponse(
        symbol=symbol_u,
        direction=query_fp.direction,
        matches=matches,
        provider="llm" if any(m.blurb_provider == "llm" for m in matches) else "template",
        query_source=query_source,
        setup_family=query_fp.setup_name,
        detail=None
        if matches
        else "No peer setups with the same direction found in recent scan history.",
    )
