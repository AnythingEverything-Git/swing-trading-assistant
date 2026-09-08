"""Morning eligibility board: NSE morning universe, stocks vs ETFs ranked separately."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from app.application.intraday.session_service import (
    build_demo_screen_bundle,
    build_persisted_screen_bundle,
)
from app.application.market_data.query_service import MarketDataQueryService
from app.domain.intraday.asset_class import morning_universe_symbols
from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1, IntradayConfigV1
from app.domain.intraday.eligibility import eligibility_flags, is_short_allowed, is_surveillance_blocked
from app.domain.intraday.engine import screen_symbol
from app.domain.intraday.rank import rank_candidates_split
from app.domain.intraday.session_calendar import IST, combine_ist
from app.domain.intraday.types import RankedCandidate, ScreenCandidate

BoardPhase = Literal["PRE_OPEN", "OR_BUILDING", "LIVE_SCREEN", "HISTORICAL"]
DataSource = Literal["demo", "persisted"]

# Demo provider synthesizes any symbol — keep morning demo snappy.
_DEMO_MORNING_CAP = 40


def resolve_board_phase(now: datetime, session_date: date) -> BoardPhase:
    local = now.astimezone(IST)
    if local.date() != session_date:
        return "HISTORICAL"
    clock = local.time()
    if clock < time(9, 15):
        return "PRE_OPEN"
    if clock < time(9, 20):
        return "OR_BUILDING"
    return "LIVE_SCREEN"


def auto_refresh_seconds(phase: BoardPhase) -> int:
    if phase == "LIVE_SCREEN":
        return 30
    if phase == "OR_BUILDING":
        return 15
    if phase == "PRE_OPEN":
        return 60
    return 120


def _ranked_payload(rows: list[RankedCandidate]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        c = r.candidate
        out.append(
            {
                "rank": r.rank,
                "symbol": c.symbol,
                "asset_class": c.asset_class,
                "direction": c.direction,
                "rvol5": str(c.rvol5),
                "or_high": str(c.opening_range.high),
                "or_low": str(c.opening_range.low),
                "or_expansion_pct": str(round(c.opening_range.expansion_pct * 100, 4)),
                "adv_value": str(c.adv_value),
                "short_allowed": c.short_allowed,
                "status": "RANKED",
            }
        )
    return out


def _eligibility_row(
    symbol: str,
    asset_class: str,
    *,
    adv_value: Decimal,
    config: IntradayConfigV1,
    reason: str,
    session_date: date,
    detail: str | None = None,
) -> dict[str, Any]:
    flags = eligibility_flags(symbol, session_date)
    return {
        "rank": None,
        "symbol": symbol,
        "asset_class": asset_class,
        "direction": None,
        "rvol5": None,
        "or_high": None,
        "or_low": None,
        "or_expansion_pct": None,
        "adv_value": str(adv_value),
        "short_allowed": flags["short_allowed"],
        "surveillance_blocked": flags["surveillance_blocked"],
        "corporate_action_blocked": flags["corporate_action_blocked"],
        "adv_ok": adv_value >= config.min_adv_inr,
        "status": reason,
        "detail": detail,
    }


async def _pre_or_eligibility_board(
    *,
    symbols: list[str],
    classes: dict[str, str],
    session_date: date,
    source: DataSource,
    query: MarketDataQueryService | None,
    config: IntradayConfigV1,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Before 09:20: liquidity / surveillance / short flags only (no ORB rank)."""
    hist_start = datetime(session_date.year, session_date.month, session_date.day, tzinfo=IST) - timedelta(days=40)
    daily_end = combine_ist(session_date, time(0, 0)) - timedelta(seconds=1)

    stocks: list[dict[str, Any]] = []
    etfs: list[dict[str, Any]] = []
    scanned = 0

    if source == "persisted" and query is not None:
        daily_map = await query.get_candles_for_symbols(symbols, "1d", hist_start, daily_end)
        for sym in symbols:
            scanned += 1
            daily = daily_map.get(sym) or []
            if daily:
                window = daily[-20:]
                total = sum((Decimal(int(c.volume or 0)) * c.close for c in window), Decimal("0"))
                adv = total / Decimal(len(window))
            else:
                adv = Decimal("0")
            blocked = is_surveillance_blocked(sym, session_date=session_date)
            flags = eligibility_flags(sym, session_date)
            if flags["corporate_action_blocked"]:
                reason = "CORPORATE_ACTION_BLOCK"
            elif blocked:
                reason = "SURVEILLANCE_BLOCKED"
            elif adv >= config.min_adv_inr:
                reason = "ADV_OK"
            else:
                reason = "LOW_ADV"
            row = _eligibility_row(
                sym,
                classes.get(sym, "STOCK"),
                adv_value=adv,
                config=config,
                reason=reason,
                session_date=session_date,
            )
            (etfs if row["asset_class"] == "ETF" else stocks).append(row)
    else:
        for sym in symbols:
            scanned += 1
            flags = eligibility_flags(sym, session_date)
            if flags["corporate_action_blocked"]:
                reason = "CORPORATE_ACTION_BLOCK"
            elif flags["surveillance_blocked"]:
                reason = "SURVEILLANCE_BLOCKED"
            else:
                reason = "WATCHLIST"
            row = _eligibility_row(
                sym,
                classes.get(sym, "STOCK"),
                adv_value=config.min_adv_inr,
                config=config,
                reason=reason,
                session_date=session_date,
                detail="Demo eligibility — full ADV after 1d seed",
            )
            (etfs if row["asset_class"] == "ETF" else stocks).append(row)

    stocks.sort(key=lambda r: Decimal(r["adv_value"] or "0"), reverse=True)
    etfs.sort(key=lambda r: Decimal(r["adv_value"] or "0"), reverse=True)
    for i, row in enumerate(stocks, start=1):
        row["rank"] = i
    for i, row in enumerate(etfs, start=1):
        row["rank"] = i

    meta = {
        "data_source": source,
        "universe_total": len(symbols),
        "scanned": scanned,
        "mode": "eligibility",
    }
    return stocks, etfs, meta


async def build_morning_board(
    *,
    session_date: date | None = None,
    source: DataSource = "persisted",
    query: MarketDataQueryService | None = None,
    equity: Decimal = Decimal("1000000"),
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
    now: datetime | None = None,
    filters: dict | None = None,
    universe: str | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """One-click morning board: NSE cash + ETFs (or a chosen universe), ranked by asset class."""
    del equity  # reserved for future arm-from-board
    clock = now or datetime.now(tz=IST)
    day = session_date or clock.astimezone(IST).date()
    if day.weekday() >= 5:
        raise ValueError("Pick a weekday session date")

    uni = (universe or "NSE_ALL").strip().upper()
    if symbols:
        ordered = [str(s).strip().upper() for s in symbols if str(s).strip()]
        from app.domain.intraday.asset_class import classify_asset_class

        classes = {s: classify_asset_class(s) for s in ordered}
    elif uni in ("NSE_ALL", "NSE_MORNING", ""):
        ordered, classes = morning_universe_symbols()
    elif uni == "DEMO_SAMPLE":
        ordered = ["ORBDEMO", "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT"]
        from app.domain.intraday.asset_class import classify_asset_class

        classes = {s: classify_asset_class(s) for s in ordered}
    else:
        from app.infrastructure.universe import get_universe
        from app.domain.intraday.asset_class import classify_asset_class

        snap = get_universe(uni).get_snapshot()
        ordered = list(snap.symbols)
        classes = {s: classify_asset_class(s) for s in ordered}

    symbols = list(ordered)
    from app.domain.universe.filters import UniverseFilterSpec, filter_symbols

    filter_spec = UniverseFilterSpec.from_mapping(filters)
    symbols, filter_decisions = filter_symbols(symbols, filter_spec, session_date=day)
    filter_drop = sum(1 for d in filter_decisions if not d.kept)
    phase = resolve_board_phase(clock, day)
    refresh = auto_refresh_seconds(phase)

    claim = (
        f"Morning universe = {uni}. "
        "Stocks and ETFs are ranked in separate Top-N pools. "
        "Persisted board screens only symbols present in the local instrument/candle DB."
    )

    if phase in ("PRE_OPEN", "OR_BUILDING"):
        if source == "demo":
            symbols = _demo_morning_slice(symbols, classes)
        elif query is not None:
            instruments = await query.instrument_repo.get_by_symbols(symbols)
            present = {inst.symbol.upper() for inst in instruments}
            symbols = [s for s in symbols if s in present] or symbols[:200]
        stocks, etfs, meta = await _pre_or_eligibility_board(
            symbols=symbols,
            classes=classes,
            session_date=day,
            source=source,
            query=query,
            config=config,
        )
        return {
            "session_date": day.isoformat(),
            "strategy_id": config.strategy_id,
            "config_hash": config.config_hash,
            "phase": phase,
            "phase_label": _phase_label(phase),
            "auto_refresh_seconds": refresh,
            "claim": claim,
            "universe_stocks": sum(1 for s in ordered if classes[s] == "STOCK"),
            "universe_etfs": sum(1 for s in ordered if classes[s] == "ETF"),
            "ranked_stocks": stocks[: config.top_n],
            "ranked_etfs": etfs[: config.top_n],
            "eligible_stocks": [r for r in stocks if r["status"] in ("ADV_OK", "WATCHLIST")],
            "eligible_etfs": [r for r in etfs if r["status"] in ("ADV_OK", "WATCHLIST")],
            "reason_counts": _count_status(stocks + etfs),
            "coverage": meta,
            "filter_coverage": {
                "universe_total": len(ordered),
                "after_filters": len(symbols),
                "dropped": filter_drop,
                "filters": filter_spec.to_dict(),
            },
            "hint": "OR closes at 09:20 IST — board switches to full RVOL ranking automatically.",
        }

    if source == "demo":
        symbols = _demo_morning_slice(symbols, classes)
        screen_inputs, candles = await build_demo_screen_bundle(symbols, day, config=config)
        meta: dict[str, Any] = {"data_source": "demo", "symbols_requested": len(symbols), "mode": "orb_screen"}
    else:
        if query is None:
            raise ValueError("persisted morning board requires MarketDataQueryService")
        instruments = await query.instrument_repo.get_by_symbols(symbols)
        present = {inst.symbol.upper() for inst in instruments}
        symbols = [s for s in symbols if s in present]
        if not symbols:
            return {
                "session_date": day.isoformat(),
                "strategy_id": config.strategy_id,
                "config_hash": config.config_hash,
                "phase": phase,
                "phase_label": _phase_label(phase),
                "auto_refresh_seconds": refresh,
                "claim": claim,
                "universe_stocks": sum(1 for s in ordered if classes[s] == "STOCK"),
                "universe_etfs": sum(1 for s in ordered if classes[s] == "ETF"),
                "ranked_stocks": [],
                "ranked_etfs": [],
                "blocked_sample": [],
                "reason_counts": {"NO_INSTRUMENTS": 1},
                "coverage": {"data_source": "persisted", "mode": "orb_screen", "symbols_requested": 0},
                "hint": "Seed instruments/1m candles first (refresh_intraday_candles.py).",
            }
        screen_inputs, candles, meta = await build_persisted_screen_bundle(query, symbols, day, config=config)
        meta = {**meta, "mode": "orb_screen"}

    screened: list[ScreenCandidate] = []
    blocked: list[dict[str, Any]] = []
    for item in screen_inputs:
        sym = str(item["symbol"]).upper()
        cand, result = screen_symbol(
            symbol=sym,
            instrument_id=str(item.get("instrument_id", sym)),
            session_date=day,
            candles_1m=candles.get(sym, []),
            prior_first_5m_volumes=list(item.get("prior_first_5m_volumes") or []),
            daily_candles=list(item.get("daily_candles") or []),
            adv_value=Decimal(str(item.get("adv_value", "0"))),
            short_allowed=bool(item.get("short_allowed", True)),
            surveillance_blocked=bool(item.get("surveillance_blocked", False)),
            corporate_action_blocked=bool(item.get("corporate_action_blocked", False)),
            spread=Decimal(str(item.get("spread", "0"))),
            tick_size=Decimal(str(item.get("tick_size", config.default_tick))),
            asset_class=str(item.get("asset_class") or classes.get(sym, "STOCK")),
            config=config,
        )
        if cand is None:
            blocked.append(
                {
                    "symbol": result.symbol,
                    "asset_class": result.asset_class or classes.get(sym, "STOCK"),
                    "reason": result.reason,
                    "detail": result.detail,
                    "rvol5": str(result.rvol5) if result.rvol5 is not None else None,
                    "direction": result.direction,
                }
            )
        else:
            screened.append(cand)

    stock_ranked, etf_ranked = rank_candidates_split(screened, config)

    reason_counts: dict[str, int] = {}
    for row in blocked:
        reason_counts[row["reason"]] = reason_counts.get(row["reason"], 0) + 1
    reason_counts["RANKED_STOCK"] = len(stock_ranked)
    reason_counts["RANKED_ETF"] = len(etf_ranked)

    return {
        "session_date": day.isoformat(),
        "strategy_id": config.strategy_id,
        "config_hash": config.config_hash,
        "phase": phase,
        "phase_label": _phase_label(phase),
        "auto_refresh_seconds": refresh,
        "claim": claim,
        "universe_stocks": sum(1 for s in ordered if classes[s] == "STOCK"),
        "universe_etfs": sum(1 for s in ordered if classes[s] == "ETF"),
        "ranked_stocks": _ranked_payload(list(stock_ranked)),
        "ranked_etfs": _ranked_payload(list(etf_ranked)),
        "blocked_sample": blocked[:40],
        "reason_counts": reason_counts,
        "coverage": {
            **meta,
            "screened": len(screened),
            "blocked": len(blocked),
            "with_1m_or_data": sum(1 for v in candles.values() if v),
        },
        "filter_coverage": {
            "universe_total": len(ordered),
            "after_filters": len(symbols),
            "dropped": filter_drop,
            "filters": filter_spec.to_dict(),
        },
        "hint": (
            "Refresh 1m: python scripts/refresh_intraday_candles.py --mode today|watermark. "
            "Names without OR bars appear under blocked / low coverage."
        ),
    }


def _demo_morning_slice(symbols: list[str], classes: dict[str, str]) -> list[str]:
    stocks = [s for s in symbols if classes.get(s) != "ETF"][:_DEMO_MORNING_CAP]
    etfs = [s for s in symbols if classes.get(s) == "ETF"][:12]
    return stocks + etfs


def _phase_label(phase: BoardPhase) -> str:
    return {
        "PRE_OPEN": "Before open — eligibility watchlist",
        "OR_BUILDING": "Opening range forming (09:15–09:20)",
        "LIVE_SCREEN": "Post-OR screen — RVOL ranks live",
        "HISTORICAL": "Historical session screen",
    }[phase]


def _count_status(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        key = str(row.get("status") or "UNKNOWN")
        out[key] = out.get(key, 0) + 1
    return out


__all__ = [
    "BoardPhase",
    "resolve_board_phase",
    "auto_refresh_seconds",
    "build_morning_board",
]
