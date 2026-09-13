"""Morning eligibility board: NSE morning universe, stocks vs ETFs ranked separately."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal, Sequence

from app.application.intraday.session_service import (
    build_demo_screen_bundle,
    build_persisted_screen_bundle,
)
from app.application.market_data.query_service import MarketDataQueryService
from app.domain.intraday.asset_class import morning_universe_symbols
from app.domain.intraday.breakout import (
    planned_entry_price,
    planned_stop_distance,
    planned_target_price,
    slippage_amount,
    stop_price,
    validate_stop_bounds,
)
from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1, IntradayConfigV1
from app.domain.intraday.eligibility import (
    corporate_action_label,
    eligibility_flags,
    is_surveillance_blocked,
)
from app.domain.intraday.engine import screen_symbol
from app.domain.intraday.rank import rank_candidates_split
from app.domain.intraday.session_calendar import (
    IST,
    combine_ist,
    default_session_date,
    is_trading_day,
)
from app.domain.intraday.decision import count_decisions, decision_from_board_row, decision_from_reason
from app.domain.intraday.sizing import can_open, size_quantity
from app.domain.intraday.types import (
    FillPlan,
    PortfolioState,
    RankedCandidate,
    RiskBudgetOverrides,
    ScreenCandidate,
)
from app.domain.market_data import Candle

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


def _last_close(candles: Sequence[Candle] | None) -> Decimal | None:
    if not candles:
        return None
    last = max(candles, key=lambda c: c.timestamp)
    return last.close


def _plan_fields(
    ranked: RankedCandidate,
    *,
    current_price: Decimal | None,
    config: IntradayConfigV1,
) -> dict[str, Any]:
    """Strategy-deduced entry / stop / 1R planning target (exits remain stop or 15:10 flatten)."""
    c = ranked.candidate
    entry = planned_entry_price(c.opening_range, c.direction, c.tick_size, config)
    planned = planned_stop_distance(c.prior_atr14, config)
    stop = stop_price(entry, c.direction, planned, c.tick_size)
    stop_distance = abs(entry - stop)
    target = planned_target_price(entry, c.direction, planned, c.tick_size)
    bound_err = validate_stop_bounds(
        entry=entry,
        stop_distance=planned,
        opening_range=c.opening_range,
        spread=c.spread,
        tick=c.tick_size,
        config=config,
    )
    if bound_err is None and (
        stop <= 0
        or (c.direction == "LONG" and not (stop < entry < target))
        or (c.direction == "SHORT" and not (target < entry < stop))
    ):
        bound_err = "invalid entry/stop/target geometry"
    entry_slip = slippage_amount(entry, c.tick_size, config)
    exit_slip = slippage_amount(entry, c.tick_size, config)
    effective = stop_distance + entry_slip + exit_slip
    risk_err = None
    if bound_err:
        risk_err = bound_err
    elif effective > planned * config.risk_invalid_mult:
        risk_err = "effective risk exceeds 1.25x planned stop"

    reason = (
        f"Rank #{ranked.rank} · RVOL5 {c.rvol5:.2f} · "
        f"{'long breakout above OR high' if c.direction == 'LONG' else 'short breakdown below OR low'}"
    )
    return {
        "current_price": str(current_price) if current_price is not None else None,
        "entry": str(entry),
        "stop": str(stop),
        "target": str(target),
        "target_label": "1R",
        "stop_distance": str(stop_distance),
        "effective_risk_per_share": str(effective),
        "quantity": 0,
        "risk_amount": None,
        "size_status": "PENDING",
        "reason": reason,
        "detail": risk_err,
        "_effective": effective,
        "_entry": entry,
        "_stop": stop,
        "_risk_err": risk_err,
    }


def _ranked_payload(
    rows: list[RankedCandidate],
    *,
    candles_by_symbol: dict[str, list[Candle]] | None = None,
    equity: Decimal = Decimal("1000000"),
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
    allocate: bool = True,
    risk_overrides: RiskBudgetOverrides | None = None,
) -> list[dict[str, Any]]:
    candles_by_symbol = candles_by_symbol or {}
    out: list[dict[str, Any]] = []
    for r in rows:
        c = r.candidate
        plan = _plan_fields(
            r,
            current_price=_last_close(candles_by_symbol.get(c.symbol)),
            config=config,
        )
        row = {
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
            "current_price": plan["current_price"],
            "entry": plan["entry"],
            "stop": plan["stop"],
            "target": plan["target"],
            "target_label": plan["target_label"],
            "stop_distance": plan["stop_distance"],
            "effective_risk_per_share": plan["effective_risk_per_share"],
            "quantity": 0,
            "risk_amount": None,
            "size_status": "PENDING",
            "reason": plan["reason"],
            "detail": plan["detail"],
            "_effective": plan["_effective"],
            "_entry": plan["_entry"],
            "_stop": plan["_stop"],
            "_risk_err": plan["_risk_err"],
            "_rank": r.rank,
            "_asset_class": c.asset_class,
            "_symbol": c.symbol,
            "_direction": c.direction,
        }
        out.append(row)

    if allocate and out:
        _allocate_quantities(out, equity=equity, config=config, risk_overrides=risk_overrides)

    for row in out:
        row["decision"] = decision_from_board_row(
            status=str(row.get("status")),
            size_status=str(row.get("size_status")) if row.get("size_status") is not None else None,
            reason=str(row.get("reason")) if row.get("reason") is not None else None,
        )
        for key in (
            "_effective",
            "_entry",
            "_stop",
            "_risk_err",
            "_rank",
            "_asset_class",
            "_symbol",
            "_direction",
        ):
            row.pop(key, None)
    return out


def _allocate_quantities(
    rows: list[dict[str, Any]],
    *,
    equity: Decimal,
    config: IntradayConfigV1,
    risk_overrides: RiskBudgetOverrides | None = None,
) -> None:
    """Distribute qty by rank (stocks then ETFs) within capital / portfolio guards."""
    overrides = risk_overrides or RiskBudgetOverrides()

    def _arm_key(row: dict[str, Any]) -> tuple[int, int]:
        return (0 if row.get("_asset_class") != "ETF" else 1, int(row.get("_rank") or 999))

    state = PortfolioState(
        equity=equity,
        max_risk_per_trade_inr=overrides.max_risk_per_trade_inr,
        max_open_risk_inr=overrides.max_open_risk_inr,
        daily_loss_lock_inr=overrides.daily_loss_lock_inr,
    )
    for row in sorted(rows, key=_arm_key):
        risk_err = row.get("_risk_err")
        if risk_err:
            row["quantity"] = 0
            row["size_status"] = "RISK_INVALID"
            row["reason"] = f"{row['reason']} · sizing blocked: {risk_err}"
            continue
        entry = Decimal(str(row["_entry"]))
        stop = Decimal(str(row["_stop"]))
        effective = Decimal(str(row["_effective"]))
        qty = size_quantity(
            equity=equity,
            effective_risk_per_share=effective,
            entry=entry,
            config=config,
            max_risk_per_trade_inr=overrides.max_risk_per_trade_inr,
        )
        if qty <= 0:
            row["quantity"] = 0
            row["size_status"] = "ZERO_QTY"
            row["reason"] = f"{row['reason']} · quantity zero after capital sizing"
            continue
        risk_amount = effective * Decimal(qty)
        plan = FillPlan(
            symbol=str(row["_symbol"]),
            direction=row["_direction"] if row["_direction"] in ("LONG", "SHORT") else "LONG",  # type: ignore[arg-type]
            rank=int(row["_rank"]),
            entry=entry,
            stop=stop,
            quantity=qty,
            stop_distance=abs(entry - stop),
            effective_risk_per_share=effective,
            trigger_bar_open=combine_ist(date.today(), time(9, 20)),
            risk_amount=risk_amount,
        )
        lock = can_open(
            state,
            plan,
            config,
            max_open_risk_inr=overrides.max_open_risk_inr,
            daily_loss_lock_inr=overrides.daily_loss_lock_inr,
        )
        if lock:
            row["quantity"] = 0
            row["risk_amount"] = None
            row["size_status"] = lock
            row["reason"] = f"{row['reason']} · not allocated ({lock.replace('_', ' ').title()})"
            continue
        row["quantity"] = qty
        row["risk_amount"] = str(risk_amount)
        row["size_status"] = "SIZED"
        row["reason"] = (
            f"{row['reason']} · qty {qty} from risk budget "
            f"(ORB {config.risk_per_trade_pct * 100:.2f}% ∩ ₹ caps; rank vs max {config.max_concurrent})"
        )
        state.open_fills.append(plan)
        state.traded_symbols.add(plan.symbol)


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
    if adv_value >= config.min_adv_inr * 2:
        adv_band = "High"
    elif adv_value >= config.min_adv_inr:
        adv_band = "Medium"
    elif adv_value > 0:
        adv_band = "Low"
    else:
        adv_band = "—"
    ca_label = corporate_action_label(symbol, session_date)
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
        "adv_band": adv_band,
        "short_allowed": flags["short_allowed"],
        "surveillance_blocked": flags["surveillance_blocked"],
        "corporate_action_blocked": flags["corporate_action_blocked"],
        "corporate_action_label": ca_label,
        "adv_ok": adv_value >= config.min_adv_inr,
        "status": reason,
        "detail": detail,
        "current_price": None,
        "entry": None,
        "stop": None,
        "target": None,
        "target_label": None,
        "quantity": None,
        "reason": detail or reason,
        "decision": decision_from_board_row(status=reason, size_status=None, reason=reason),
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
    risk_overrides: RiskBudgetOverrides | None = None,
) -> dict[str, Any]:
    """One-click morning board: NSE cash + ETFs (or a chosen universe), ranked by asset class."""
    clock = now or datetime.now(tz=IST)
    day = session_date or default_session_date(clock)
    if not is_trading_day(day):
        raise ValueError("Pick a trading day (weekends and NSE holidays are closed)")

    uni = (universe or "NIFTY_500").strip().upper() or "NIFTY_500"
    if symbols:
        ordered = [str(s).strip().upper() for s in symbols if str(s).strip()]
        from app.domain.intraday.asset_class import classify_asset_class

        classes = {s: classify_asset_class(s) for s in ordered}
    elif uni in ("NSE_ALL", "NSE_MORNING"):
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
        "Persisted board screens only symbols present in the local instrument/candle DB. "
        "Quantity uses account capital + ORB V1 risk rules, allocated by rank."
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
            "decision_counts": count_decisions(stocks[: config.top_n] + etfs[: config.top_n]),
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
                    "decision": decision_from_reason(result.reason),
                }
            )
        else:
            screened.append(cand)

    stock_ranked, etf_ranked = rank_candidates_split(screened, config)

    # Shared capital pool across stocks + ETFs (same order as session engine).
    combined = _ranked_payload(
        list(stock_ranked) + list(etf_ranked),
        candles_by_symbol=candles,
        equity=equity,
        config=config,
        allocate=True,
        risk_overrides=risk_overrides,
    )
    by_symbol = {r["symbol"]: r for r in combined}
    stock_rows = [by_symbol[r.candidate.symbol] for r in stock_ranked if r.candidate.symbol in by_symbol]
    etf_rows = [by_symbol[r.candidate.symbol] for r in etf_ranked if r.candidate.symbol in by_symbol]

    reason_counts: dict[str, int] = {}
    for row in blocked:
        reason_counts[row["reason"]] = reason_counts.get(row["reason"], 0) + 1
    reason_counts["RANKED_STOCK"] = len(stock_rows)
    reason_counts["RANKED_ETF"] = len(etf_rows)
    reason_counts["SIZED"] = sum(1 for r in combined if r.get("size_status") == "SIZED")
    decision_counts = count_decisions(combined + blocked)

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
        "ranked_stocks": stock_rows,
        "ranked_etfs": etf_rows,
        "blocked_sample": blocked[:40],
        "reason_counts": reason_counts,
        "decision_counts": decision_counts,
        "coverage": {
            **meta,
            "screened": len(screened),
            "blocked": len(blocked),
            "with_1m_or_data": sum(1 for v in candles.values() if v),
            "equity": str(equity),
            "risk_overrides": {
                "max_risk_per_trade_inr": str(risk_overrides.max_risk_per_trade_inr)
                if risk_overrides and risk_overrides.max_risk_per_trade_inr is not None
                else None,
                "max_open_risk_inr": str(risk_overrides.max_open_risk_inr)
                if risk_overrides and risk_overrides.max_open_risk_inr is not None
                else None,
                "daily_loss_lock_inr": str(risk_overrides.daily_loss_lock_inr)
                if risk_overrides and risk_overrides.daily_loss_lock_inr is not None
                else None,
            },
        },
        "filter_coverage": {
            "universe_total": len(ordered),
            "after_filters": len(symbols),
            "dropped": filter_drop,
            "filters": filter_spec.to_dict(),
        },
        "hint": (
            "Confirmed = Top-N RVOL screen after OR. "
            "Entry/SL/Target from ORB V1 (Target = 1R planning price). "
            "Exits remain stop or forced flatten 15:10 — V1 does not auto-take profit at Target. "
            "Capital available ≠ permission to risk it — absolute ₹ caps layer on CONFIG_V1 %. "
            "Refresh 1m: python scripts/refresh_intraday_candles.py --mode today|watermark."
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
