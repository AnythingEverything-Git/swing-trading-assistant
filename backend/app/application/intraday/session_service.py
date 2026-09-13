"""Run one intraday ORB session from demo or persisted 1m candles."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.application.market_data.query_service import MarketDataQueryService
from app.domain.intraday.asset_class import classify_asset_class
from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1, IntradayConfigV1
from app.domain.intraday.eligibility import eligibility_flags
from app.domain.intraday.engine import prior_day_atr14, run_session
from app.domain.intraday.session_calendar import default_session_date, is_trading_day, is_weekday
from app.domain.intraday.decision import count_decisions, decision_from_reason
from app.domain.intraday.types import SessionReport
from app.domain.market_data import Candle
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider

IST = ZoneInfo("Asia/Kolkata")
DataSource = Literal["demo", "persisted"]

# In-memory session store for MVP API (DB tables come later).
_SESSIONS: dict[str, dict[str, Any]] = {}


def _session_window(session_date: date) -> tuple[datetime, datetime]:
    start = datetime(session_date.year, session_date.month, session_date.day, 9, 15, tzinfo=IST)
    end = datetime(session_date.year, session_date.month, session_date.day, 15, 29, tzinfo=IST)
    return start, end


def _or_volume_and_range(m1: list[Candle]) -> tuple[int, Decimal | None, Decimal | None]:
    or_vol = 0
    or_high = None
    or_low = None
    for c in m1:
        ts = c.timestamp.astimezone(IST)
        if ts.hour == 9 and 15 <= ts.minute < 20:
            or_vol += int(c.volume or 0)
            or_high = c.high if or_high is None else max(or_high, c.high)
            or_low = c.low if or_low is None else min(or_low, c.low)
    return or_vol, or_high, or_low


def _first_5m_volumes_by_session(candles_1m: list[Candle]) -> dict[date, int]:
    by_day: dict[date, int] = {}
    for c in candles_1m:
        ts = c.timestamp.astimezone(IST)
        if ts.hour == 9 and 15 <= ts.minute < 20:
            by_day[ts.date()] = by_day.get(ts.date(), 0) + int(c.volume or 0)
    return by_day


def _adv_value_inr(daily: list[Candle]) -> Decimal:
    if not daily:
        return Decimal("0")
    window = daily[-20:]
    total = Decimal("0")
    for c in window:
        vol = Decimal(int(c.volume or 0))
        total += vol * c.close
    return total / Decimal(len(window))


async def build_demo_screen_bundle(
    symbols: list[str],
    session_date: date,
    provider: DemoMarketDataProvider | None = None,
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> tuple[list[dict], dict[str, list[Candle]]]:
    """Load demo 1m + synthetic ATR priors for a tradeable screen."""
    provider = provider or DemoMarketDataProvider()
    start, end = _session_window(session_date)

    screen_inputs: list[dict] = []
    candles_1m_by_symbol: dict[str, list[Candle]] = {}

    for symbol in symbols:
        sym = symbol.upper()
        m1 = await provider.get_candles(sym, "1m", start, end)
        candles_1m_by_symbol[sym] = m1

        or_vol, or_high, or_low = _or_volume_and_range(m1)
        prior = [max(1, or_vol // 3)] * config.rvol_lookback_sessions
        or_range = (or_high - or_low) if or_high is not None and or_low is not None else Decimal("1")
        target_atr = max(or_range * Decimal("8"), Decimal("1"))
        px = m1[0].close if m1 else Decimal("100")
        daily = _synth_daily_with_atr(sym, session_date, px, target_atr)

        flags = eligibility_flags(sym, session_date)
        screen_inputs.append(
            {
                "symbol": sym,
                "instrument_id": sym,
                "prior_first_5m_volumes": prior,
                "daily_candles": daily,
                "adv_value": Decimal("100000000"),
                "short_allowed": flags["short_allowed"],
                "surveillance_blocked": flags["surveillance_blocked"],
                "corporate_action_blocked": flags["corporate_action_blocked"],
                "spread": Decimal("0.05"),
                "tick_size": Decimal("0.05"),
                "asset_class": classify_asset_class(sym),
            }
        )
    return screen_inputs, candles_1m_by_symbol


async def build_persisted_screen_bundle(
    query: MarketDataQueryService,
    symbols: list[str],
    session_date: date,
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> tuple[list[dict], dict[str, list[Candle]], dict[str, Any]]:
    """Load 1m + 1d from Postgres for ORB screening (batched candle queries)."""
    start, end = _session_window(session_date)
    hist_start = datetime(session_date.year, session_date.month, session_date.day, tzinfo=IST) - timedelta(days=40)
    daily_end = datetime(session_date.year, session_date.month, session_date.day, 0, 0, tzinfo=IST) - timedelta(
        seconds=1
    )

    syms = [s.upper() for s in symbols]
    m1_map = await query.get_candles_for_symbols(syms, "1m", start, end)
    # Accuracy-identical to scanning full hist 1m: only OR minutes (09:15–09:19) are used for RVOL.
    prior_maps = await query.get_first_5m_volumes_for_symbols(
        syms, hist_start=hist_start, session_start=start
    )
    daily_map = await query.get_candles_for_symbols(syms, "1d", hist_start, daily_end)

    screen_inputs: list[dict] = []
    candles_1m_by_symbol: dict[str, list[Candle]] = {}
    coverage = {"with_1m": 0, "with_or": 0, "with_atr": 0}

    for sym in syms:
        m1 = m1_map.get(sym) or []
        prior_map = prior_maps.get(sym) or {}
        daily = daily_map.get(sym) or []
        candles_1m_by_symbol[sym] = m1
        if m1:
            coverage["with_1m"] += 1

        prior_dates = sorted(d for d in prior_map if d < session_date and is_weekday(d))
        prior_vols = [prior_map[d] for d in prior_dates[-config.rvol_lookback_sessions :]]

        or_vol, _or_high, _or_low = _or_volume_and_range(m1)
        if or_vol > 0:
            coverage["with_or"] += 1

        atr = prior_day_atr14(daily, config.atr_period)
        if atr is not None:
            coverage["with_atr"] += 1
            daily_for_screen = daily
        else:
            px = m1[0].close if m1 else Decimal("100")
            daily_for_screen = _synth_daily_with_atr(sym, session_date, px, px * Decimal("0.02"))

        adv = _adv_value_inr(daily) if daily else Decimal("0")
        # Minute-only seeds (demo backfill) often lack 1d ADV — don't block the desk.
        if adv < config.min_adv_inr and or_vol > 0:
            adv = config.min_adv_inr

        flags = eligibility_flags(sym, session_date)
        screen_inputs.append(
            {
                "symbol": sym,
                "instrument_id": sym,
                "prior_first_5m_volumes": prior_vols,
                "daily_candles": daily_for_screen,
                "adv_value": adv,
                "short_allowed": flags["short_allowed"],
                "surveillance_blocked": flags["surveillance_blocked"],
                "corporate_action_blocked": flags["corporate_action_blocked"],
                "spread": Decimal("0.05"),
                "tick_size": Decimal("0.05"),
                "asset_class": classify_asset_class(sym),
            }
        )

    meta = {
        "data_source": "persisted",
        "symbols_requested": len(syms),
        **coverage,
    }
    return screen_inputs, candles_1m_by_symbol, meta


def _synth_daily_with_atr(symbol: str, session_date: date, px: Decimal, target_atr: Decimal) -> list[Candle]:
    out: list[Candle] = []
    half = target_atr / Decimal("2")
    for i in range(25, 0, -1):
        day = session_date - timedelta(days=i)
        if day.weekday() >= 5:
            continue
        ts = datetime(day.year, day.month, day.day, tzinfo=IST)
        out.append(
            Candle(
                symbol=symbol,
                exchange="DEMO",
                instrument_id=None,
                timeframe="1d",
                timestamp=ts,
                open=px,
                high=px + half,
                low=max(Decimal("0.01"), px - half),
                close=px,
                volume=1_000_000,
            )
        )
    return out


async def run_intraday_session(
    *,
    session_date: date | None = None,
    symbols: list[str] | None = None,
    equity: Decimal = Decimal("1000000"),
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
    source: DataSource = "demo",
    query: MarketDataQueryService | None = None,
    session_repo: Any | None = None,
) -> tuple[str, SessionReport, dict[str, Any]]:
    """Run ORB session from demo or persisted candles; store report in memory (+ DB if repo)."""
    day = session_date or default_session_date()
    if not is_trading_day(day):
        raise ValueError("Pick a trading day (weekends and NSE holidays are closed)")

    if source == "persisted":
        if query is None:
            raise ValueError("persisted source requires MarketDataQueryService")
        syms = [s.upper() for s in (symbols or ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC"])]
        screen_inputs, candles, meta = await build_persisted_screen_bundle(query, syms, day, config=config)
    else:
        syms = [s.upper() for s in (symbols or ["ORBDEMO", "RELIANCE", "TCS", "INFY", "HDFCBANK"])]
        # Demo synthesizes every bar — keep large universes (NSE morning) snappy.
        demo_cap = 52
        if len(syms) > demo_cap:
            from app.domain.intraday.asset_class import classify_asset_class

            stocks = [s for s in syms if classify_asset_class(s) != "ETF"][:40]
            etfs = [s for s in syms if classify_asset_class(s) == "ETF"][:12]
            syms = stocks + etfs
        screen_inputs, candles = await build_demo_screen_bundle(syms, day, config=config)
        meta = {"data_source": "demo", "symbols_requested": len(syms), "demo_capped": len(symbols or []) > demo_cap}

    report = run_session(
        session_date=day,
        equity=equity,
        screen_inputs=screen_inputs,
        candles_1m_by_symbol=candles,
        config=config,
    )
    session_id = str(uuid4())
    created_at = datetime.now(tz=IST)
    payload = session_report_to_dict(report, meta)
    payload["id"] = session_id
    realized = sum((t.pnl for t in report.closed_trades), Decimal("0"))
    _SESSIONS[session_id] = {
        "id": session_id,
        "report": report,
        "meta": meta,
        "created_at": created_at.isoformat(),
        "result_payload": payload,
    }
    if session_repo is not None:
        await session_repo.save(
            session_id=session_id,
            created_at=created_at,
            session_date=day,
            strategy_id=report.strategy_id,
            config_hash=report.config_hash,
            data_source=str(meta.get("data_source") or source),
            equity=equity,
            coverage_eligible=report.coverage_eligible,
            coverage_total=report.coverage_total,
            fill_count=len(report.fills),
            realized_pnl=realized,
            result_payload=payload,
            meta=meta,
        )
    return session_id, report, meta


async def load_session(
    session_id: str,
    *,
    session_repo: Any | None = None,
) -> dict[str, Any] | None:
    """Load from memory first, then DB."""
    cached = _SESSIONS.get(session_id)
    if cached is not None:
        return cached
    if session_repo is None:
        return None
    row = await session_repo.get(session_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "meta": row.meta or {},
        "result_payload": row.result_payload,
        "report": None,
    }


async def run_demo_session(
    *,
    session_date: date | None = None,
    symbols: list[str] | None = None,
    equity: Decimal = Decimal("1000000"),
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> tuple[str, SessionReport]:
    """Backward-compatible demo runner."""
    session_id, report, _meta = await run_intraday_session(
        session_date=session_date,
        symbols=symbols,
        equity=equity,
        config=config,
        source="demo",
    )
    return session_id, report


def get_stored_session(session_id: str) -> dict[str, Any] | None:
    return _SESSIONS.get(session_id)


def session_report_to_dict(report: SessionReport, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    reason_counts: dict[str, int] = {}
    for r in report.symbol_results:
        reason_counts[r.reason] = reason_counts.get(r.reason, 0) + 1
    coverage_pct = (
        round(100.0 * report.coverage_eligible / report.coverage_total, 2)
        if report.coverage_total
        else 0.0
    )

    def _ranked_row(r) -> dict[str, Any]:
        c = r.candidate
        return {
            "rank": r.rank,
            "symbol": c.symbol,
            "asset_class": c.asset_class,
            "direction": c.direction,
            "rvol5": str(c.rvol5),
            "or_high": str(c.opening_range.high),
            "or_low": str(c.opening_range.low),
            "or_expansion_pct": str(c.opening_range.expansion_pct),
            "adv_value": str(c.adv_value),
            "decision": "WATCH",
            "status": "RANKED",
        }

    symbol_results = [
        {
            "symbol": r.symbol,
            "reason": r.reason,
            "rank": r.rank,
            "rvol5": str(r.rvol5) if r.rvol5 is not None else None,
            "direction": r.direction,
            "detail": r.detail,
            "asset_class": r.asset_class,
            "decision": decision_from_reason(r.reason),
        }
        for r in sorted(report.symbol_results, key=lambda x: (x.rank is None, x.rank or 999, x.symbol))
    ]

    body: dict[str, Any] = {
        "session_date": report.session_date.isoformat(),
        "strategy_id": report.strategy_id,
        "config_hash": report.config_hash,
        "coverage_eligible": report.coverage_eligible,
        "coverage_total": report.coverage_total,
        "coverage_pct": coverage_pct,
        "reason_counts": reason_counts,
        "decision_counts": count_decisions(symbol_results),
        "ranked_stocks": [_ranked_row(r) for r in report.ranked_stocks],
        "ranked_etfs": [_ranked_row(r) for r in report.ranked_etfs],
        "symbol_results": symbol_results,
        "fills": [
            {
                "symbol": f.symbol,
                "direction": f.direction,
                "rank": f.rank,
                "entry": str(f.entry),
                "stop": str(f.stop),
                "quantity": f.quantity,
                "trigger_bar_open": f.trigger_bar_open.isoformat(),
                "stop_distance": str(f.stop_distance),
                "risk_amount": str(f.risk_amount),
                "effective_risk_per_share": str(f.effective_risk_per_share),
            }
            for f in report.fills
        ],
        "closed_trades": [
            {
                "symbol": t.fill.symbol,
                "direction": t.fill.direction,
                "entry": str(t.fill.entry),
                "exit": str(t.exit_price),
                "exit_reason": t.exit_reason,
                "pnl": str(t.pnl),
                "exit_time": t.exit_time.isoformat(),
                "quantity": t.fill.quantity,
                "stop": str(t.fill.stop),
                "mfe": str(t.mfe),
                "mae": str(t.mae),
                "giveback": str(t.giveback) if t.giveback is not None else None,
                "entry_time": t.fill.trigger_bar_open.isoformat(),
            }
            for t in report.closed_trades
        ],
    }
    if meta:
        body["data_source"] = meta.get("data_source")
        body["coverage_detail"] = {k: v for k, v in meta.items() if k != "data_source"}
    return body


async def load_session_chart(
    session_id: str,
    symbol: str,
    *,
    query: MarketDataQueryService | None = None,
    session_repo: Any | None = None,
    timeframe: str = "1m",
) -> dict[str, Any] | None:
    """Candles + OR / entry / stop levels for the Intraday desk chart."""
    from app.infrastructure.market_data.demo_provider import _aggregate_5m

    stored = await load_session(session_id, session_repo=session_repo)
    if stored is None:
        return None

    payload = stored.get("result_payload")
    if payload is None and stored.get("report") is not None:
        payload = session_report_to_dict(stored["report"], stored.get("meta"))
    if not isinstance(payload, dict):
        return None

    tf = timeframe if timeframe in {"1m", "5m"} else "1m"
    sym = symbol.strip().upper()
    session_date = date.fromisoformat(str(payload["session_date"]))
    source = str(payload.get("data_source") or (stored.get("meta") or {}).get("data_source") or "demo")
    start, end = _session_window(session_date)

    if source == "persisted":
        if query is None:
            raise ValueError("persisted chart requires MarketDataQueryService")
        candles_1m = await query.get_candles(sym, "1m", start, end)
    else:
        candles_1m = await DemoMarketDataProvider().get_candles(sym, "1m", start, end)

    candles = candles_1m if tf == "1m" else _aggregate_5m(candles_1m)

    or_high: Decimal | None = None
    or_low: Decimal | None = None
    or_open: Decimal | None = None
    for c in candles_1m:
        ts = c.timestamp.astimezone(IST)
        if ts.hour == 9 and 15 <= ts.minute < 20:
            or_high = c.high if or_high is None else max(or_high, c.high)
            or_low = c.low if or_low is None else min(or_low, c.low)
            if or_open is None:
                or_open = c.open

    fill = next((f for f in payload.get("fills") or [] if f.get("symbol") == sym), None)
    closed = next((t for t in payload.get("closed_trades") or [] if t.get("symbol") == sym), None)
    row = next((r for r in payload.get("symbol_results") or [] if r.get("symbol") == sym), None)

    trigger_index: int | None = None
    if fill and fill.get("trigger_bar_open"):
        trigger_raw = str(fill["trigger_bar_open"])
        for idx, c in enumerate(candles):
            if c.timestamp.isoformat().startswith(trigger_raw[:19]) or c.timestamp.isoformat() == trigger_raw:
                trigger_index = idx
                break
            if c.timestamp.astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S") == trigger_raw[:19]:
                trigger_index = idx
                break

    return {
        "session_id": session_id,
        "symbol": sym,
        "session_date": session_date.isoformat(),
        "data_source": source,
        "timeframe": tf,
        "direction": (fill or row or {}).get("direction"),
        "reason": (row or {}).get("reason") if row else None,
        "or_open": str(or_open) if or_open is not None else None,
        "or_high": str(or_high) if or_high is not None else None,
        "or_low": str(or_low) if or_low is not None else None,
        "entry": fill.get("entry") if fill else None,
        "stop": fill.get("stop") if fill else (closed.get("stop") if closed else None),
        "exit": closed.get("exit") if closed else None,
        "trigger_index": trigger_index,
        "candles": [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": str(c.open),
                "high": str(c.high),
                "low": str(c.low),
                "close": str(c.close),
                "volume": int(c.volume or 0),
            }
            for c in candles
        ],
    }


__all__ = [
    "run_demo_session",
    "run_intraday_session",
    "load_session",
    "get_stored_session",
    "session_report_to_dict",
    "load_session_chart",
    "build_demo_screen_bundle",
    "build_persisted_screen_bundle",
]
