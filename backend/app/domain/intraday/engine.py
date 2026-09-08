"""Session engine: screen → arm → trigger → manage → flatten."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from app.domain.intraday.breakout import (
    find_breakout_fill,
    planned_stop_distance,
    slippage_amount,
    stop_price,
    validate_stop_bounds,
)
from app.domain.intraday.config_v1 import IntradayConfigV1, DEFAULT_CONFIG_V1
from app.domain.intraday.opening_range import build_opening_range, direction_from_or
from app.domain.intraday.rank import rank_candidates_split
from app.domain.intraday.asset_class import classify_asset_class
from app.domain.intraday.rvol import compute_rvol5
from app.domain.intraday.session_calendar import combine_ist, to_ist
from app.domain.intraday.sizing import can_open, size_quantity
from app.domain.intraday.types import (
    ClosedTrade,
    FillPlan,
    PortfolioState,
    RankedCandidate,
    ScreenCandidate,
    SessionReport,
    SymbolResult,
)
from app.domain.market_data import Candle
from app.domain.market_data.indicators import atr


def prior_day_atr14(daily_candles: Sequence[Candle], period: int = 14) -> Decimal | None:
    """ATR14 from completed daily bars (last value)."""
    if len(daily_candles) < period:
        return None
    series = atr(list(daily_candles), period)
    value = series[-1]
    return value


def screen_symbol(
    *,
    symbol: str,
    instrument_id: str,
    session_date: date,
    candles_1m: Sequence[Candle],
    prior_first_5m_volumes: Sequence[int],
    daily_candles: Sequence[Candle],
    adv_value: Decimal,
    short_allowed: bool = True,
    surveillance_blocked: bool = False,
    corporate_action_blocked: bool = False,
    spread: Decimal = Decimal("0"),
    mid_price: Decimal | None = None,
    tick_size: Decimal = Decimal("0.05"),
    asset_class: str = "STOCK",
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> tuple[ScreenCandidate | None, SymbolResult]:
    if surveillance_blocked:
        return None, SymbolResult(symbol=symbol, reason="SURVEILLANCE_BLOCKED", asset_class=asset_class)  # type: ignore[arg-type]
    if corporate_action_blocked:
        return None, SymbolResult(symbol=symbol, reason="CORPORATE_ACTION_BLOCK", asset_class=asset_class)  # type: ignore[arg-type]

    mid = mid_price
    if mid is None or mid <= 0:
        # Fall back to last daily close approximation from ATR path later; use OR open after build.
        mid = None
    if mid is not None and mid > 0 and spread > 0:
        if spread / mid > config.max_spread_pct:
            return None, SymbolResult(
                symbol=symbol,
                reason="SPREAD_TOO_WIDE",
                detail=f"spread/mid={spread / mid}",
                asset_class=asset_class,  # type: ignore[arg-type]
            )

    orng = build_opening_range(symbol, session_date, candles_1m, config)
    if orng is None:
        return None, SymbolResult(
            symbol=symbol, reason="INSUFFICIENT_HISTORY", detail="missing OR", asset_class=asset_class  # type: ignore[arg-type]
        )

    if mid is None and orng.open > 0 and spread > 0:
        if spread / orng.open > config.max_spread_pct:
            return None, SymbolResult(
                symbol=symbol,
                reason="SPREAD_TOO_WIDE",
                detail=f"spread/or_open={spread / orng.open}",
                asset_class=asset_class,  # type: ignore[arg-type]
            )

    direction = direction_from_or(orng, tick_size, config)
    if direction is None:
        return None, SymbolResult(symbol=symbol, reason="DOJI", asset_class=asset_class)  # type: ignore[arg-type]

    if direction == "SHORT" and not short_allowed:
        return None, SymbolResult(
            symbol=symbol, reason="SHORT_NOT_PERMITTED", direction=direction, asset_class=asset_class  # type: ignore[arg-type]
        )

    rvol = compute_rvol5(orng.volume, prior_first_5m_volumes, config)
    if rvol is None:
        return None, SymbolResult(
            symbol=symbol, reason="INSUFFICIENT_HISTORY", detail="RVOL lookback", asset_class=asset_class  # type: ignore[arg-type]
        )

    if rvol < config.min_rvol5:
        return None, SymbolResult(
            symbol=symbol, reason="INSUFFICIENT_RVOL", rvol5=rvol, direction=direction, asset_class=asset_class  # type: ignore[arg-type]
        )

    if adv_value < config.min_adv_inr:
        return None, SymbolResult(
            symbol=symbol,
            reason="INSUFFICIENT_LIQUIDITY",
            rvol5=rvol,
            direction=direction,
            asset_class=asset_class,  # type: ignore[arg-type]
        )

    prior_atr = prior_day_atr14(daily_candles, config.atr_period)
    if prior_atr is None or prior_atr <= 0:
        return None, SymbolResult(
            symbol=symbol, reason="INSUFFICIENT_HISTORY", detail="ATR14", asset_class=asset_class  # type: ignore[arg-type]
        )

    ac = "ETF" if asset_class == "ETF" else "STOCK"
    candidate = ScreenCandidate(
        symbol=symbol.upper(),
        instrument_id=instrument_id,
        direction=direction,
        opening_range=orng,
        rvol5=rvol,
        adv_value=adv_value,
        prior_atr14=prior_atr,
        short_allowed=short_allowed,
        spread=spread,
        tick_size=tick_size,
        asset_class=ac,  # type: ignore[arg-type]
    )
    return candidate, SymbolResult(
        symbol=symbol,
        reason="RANKED_ARMED",
        rvol5=rvol,
        direction=direction,
        asset_class=ac,  # type: ignore[arg-type]
    )


def build_fill_plan(
    ranked: RankedCandidate,
    entry: Decimal,
    trigger_bar: Candle,
    equity: Decimal,
    config: IntradayConfigV1,
) -> tuple[FillPlan | None, str | None]:
    c = ranked.candidate
    planned = planned_stop_distance(c.prior_atr14, config)
    tick = c.tick_size
    entry_slip = slippage_amount(entry, tick, config)
    exit_slip = slippage_amount(entry, tick, config)
    stop = stop_price(entry, c.direction, planned, tick)
    stop_distance = abs(entry - stop)
    bound_err = validate_stop_bounds(
        entry=entry,
        stop_distance=stop_distance,
        opening_range=c.opening_range,
        spread=c.spread,
        tick=tick,
        config=config,
    )
    if bound_err:
        return None, bound_err

    effective = stop_distance + entry_slip + exit_slip
    if effective > planned * config.risk_invalid_mult:
        return None, "effective risk exceeds 1.25x planned stop"

    qty = size_quantity(equity=equity, effective_risk_per_share=effective, entry=entry, config=config)
    if qty <= 0:
        return None, "quantity zero after sizing"

    risk_amount = effective * Decimal(qty)
    return (
        FillPlan(
            symbol=c.symbol,
            direction=c.direction,
            rank=ranked.rank,
            entry=entry,
            stop=stop,
            quantity=qty,
            stop_distance=stop_distance,
            effective_risk_per_share=effective,
            trigger_bar_open=to_ist(trigger_bar.timestamp),
            risk_amount=risk_amount,
        ),
        None,
    )


def update_excursions(
    *,
    direction: str,
    entry: Decimal,
    quantity: int,
    bar: Candle,
    mfe: Decimal,
    mae: Decimal,
) -> tuple[Decimal, Decimal]:
    """Track max favorable / max adverse excursion in INR (qty-scaled)."""
    if direction == "LONG":
        fav = (bar.high - entry) * Decimal(quantity)
        adv = (entry - bar.low) * Decimal(quantity)
    else:
        fav = (entry - bar.low) * Decimal(quantity)
        adv = (bar.high - entry) * Decimal(quantity)
    return max(mfe, max(Decimal("0"), fav)), max(mae, max(Decimal("0"), adv))


def manage_open_to_bar(
    fill: FillPlan,
    bar: Candle,
    config: IntradayConfigV1,
    *,
    mfe: Decimal = Decimal("0"),
    mae: Decimal = Decimal("0"),
) -> ClosedTrade | None:
    """Apply stop on this 1m bar; conservative if both sides possible."""
    ts = to_ist(bar.timestamp)
    forced = combine_ist(fill.trigger_bar_open.date(), config.forced_exit)
    # Stop check
    if fill.direction == "LONG":
        hit_stop = bar.low <= fill.stop
        if hit_stop:
            exit_px = fill.stop - slippage_amount(fill.stop, Decimal("0.05"), config)
            pnl = (exit_px - fill.entry) * Decimal(fill.quantity)
            return ClosedTrade(
                fill=fill,
                exit_price=exit_px,
                exit_reason="STOP",
                exit_time=ts,
                pnl=pnl,
                mfe=mfe,
                mae=mae,
            )
    else:
        hit_stop = bar.high >= fill.stop
        if hit_stop:
            exit_px = fill.stop + slippage_amount(fill.stop, Decimal("0.05"), config)
            pnl = (fill.entry - exit_px) * Decimal(fill.quantity)
            return ClosedTrade(
                fill=fill,
                exit_price=exit_px,
                exit_reason="STOP",
                exit_time=ts,
                pnl=pnl,
                mfe=mfe,
                mae=mae,
            )

    if ts >= forced:
        # Flatten at bar open if at/after forced exit minute
        exit_px = bar.open
        if fill.direction == "LONG":
            exit_px = bar.open - slippage_amount(bar.open, Decimal("0.05"), config)
            pnl = (exit_px - fill.entry) * Decimal(fill.quantity)
        else:
            exit_px = bar.open + slippage_amount(bar.open, Decimal("0.05"), config)
            pnl = (fill.entry - exit_px) * Decimal(fill.quantity)
        return ClosedTrade(
            fill=fill,
            exit_price=exit_px,
            exit_reason="EOD_EXIT",
            exit_time=ts,
            pnl=pnl,
            mfe=mfe,
            mae=mae,
        )
    return None


def run_session(
    *,
    session_date: date,
    equity: Decimal,
    screen_inputs: Sequence[dict],
    candles_1m_by_symbol: Mapping[str, Sequence[Candle]],
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> SessionReport:
    """Run one session.

    Each screen_inputs item keys:
      symbol, instrument_id, prior_first_5m_volumes, daily_candles,
      adv_value, short_allowed?, spread?, tick_size?
    """
    results: list[SymbolResult] = []
    screened: list[ScreenCandidate] = []

    for item in screen_inputs:
        symbol = str(item["symbol"]).upper()
        candles = candles_1m_by_symbol.get(symbol, [])
        asset_class = str(item.get("asset_class") or classify_asset_class(symbol))
        cand, result = screen_symbol(
            symbol=symbol,
            instrument_id=str(item.get("instrument_id", symbol)),
            session_date=session_date,
            candles_1m=candles,
            prior_first_5m_volumes=list(item.get("prior_first_5m_volumes") or []),
            daily_candles=list(item.get("daily_candles") or []),
            adv_value=Decimal(str(item.get("adv_value", "0"))),
            short_allowed=bool(item.get("short_allowed", True)),
            surveillance_blocked=bool(item.get("surveillance_blocked", False)),
            corporate_action_blocked=bool(item.get("corporate_action_blocked", False)),
            spread=Decimal(str(item.get("spread", "0"))),
            mid_price=Decimal(str(item["mid_price"])) if item.get("mid_price") is not None else None,
            tick_size=Decimal(str(item.get("tick_size", config.default_tick))),
            asset_class=asset_class,
            config=config,
        )
        if cand is None:
            results.append(result)
        else:
            screened.append(cand)

    stock_ranked, etf_ranked = rank_candidates_split(screened, config)
    ranked = list(stock_ranked) + list(etf_ranked)
    ranked_symbols = {r.candidate.symbol for r in ranked}
    for cand in screened:
        if cand.symbol not in ranked_symbols:
            results.append(
                SymbolResult(
                    symbol=cand.symbol,
                    reason="NOT_IN_TOP_N",
                    rvol5=cand.rvol5,
                    direction=cand.direction,
                    asset_class=cand.asset_class,
                )
            )

    for r in ranked:
        results.append(
            SymbolResult(
                symbol=r.candidate.symbol,
                reason="RANKED_ARMED",
                rank=r.rank,
                rvol5=r.candidate.rvol5,
                direction=r.candidate.direction,
                asset_class=r.candidate.asset_class,
            )
        )

    state = PortfolioState(equity=equity)
    fills: list[FillPlan] = []
    pending = {r.candidate.symbol: r for r in ranked}
    open_by_symbol: dict[str, FillPlan] = {}

    def _arm_key(r: RankedCandidate) -> tuple[int, int]:
        # Stocks then ETFs; within class by class-local rank.
        return (0 if r.candidate.asset_class != "ETF" else 1, r.rank)

    # Resolve entries once per armed symbol (rank order), then simulate management on a shared clock.
    for ranked_c in sorted(pending.values(), key=_arm_key):
        sym = ranked_c.candidate.symbol
        hit = find_breakout_fill(
            ranked_c,
            candles_1m_by_symbol.get(sym, []),
            session_date,
            config,
        )
        if hit is None:
            results.append(
                SymbolResult(
                    symbol=sym,
                    reason="BREAKOUT_NOT_TRIGGERED",
                    rank=ranked_c.rank,
                    rvol5=ranked_c.candidate.rvol5,
                    direction=ranked_c.candidate.direction,
                    asset_class=ranked_c.candidate.asset_class,
                )
            )
            continue
        entry, trigger_bar = hit
        plan, err = build_fill_plan(ranked_c, entry, trigger_bar, state.equity, config)
        if plan is None:
            state.traded_symbols.add(sym)
            results.append(
                SymbolResult(
                    symbol=sym,
                    reason="RISK_INVALID",
                    rank=ranked_c.rank,
                    rvol5=ranked_c.candidate.rvol5,
                    direction=ranked_c.candidate.direction,
                    detail=err,
                    asset_class=ranked_c.candidate.asset_class,
                )
            )
            continue
        lock = can_open(state, plan, config)
        state.traded_symbols.add(sym)
        if lock:
            results.append(
                SymbolResult(
                    symbol=sym,
                    reason=lock,  # type: ignore[arg-type]
                    rank=ranked_c.rank,
                    rvol5=ranked_c.candidate.rvol5,
                    direction=ranked_c.candidate.direction,
                    asset_class=ranked_c.candidate.asset_class,
                )
            )
            continue
        fills.append(plan)
        open_by_symbol[sym] = plan
        state.open_fills.append(plan)
        results.append(
            SymbolResult(
                symbol=sym,
                reason="TRADED",
                rank=ranked_c.rank,
                rvol5=ranked_c.candidate.rvol5,
                direction=ranked_c.candidate.direction,
                asset_class=ranked_c.candidate.asset_class,
            )
        )

    # Build union of timestamps from entry → forced exit for open trade management
    all_ts: set = set()
    for fill in fills:
        for bar in candles_1m_by_symbol.get(fill.symbol, []):
            ts = to_ist(bar.timestamp)
            if fill.trigger_bar_open <= ts <= combine_ist(session_date, config.forced_exit):
                all_ts.add(ts)

    still_open: dict[str, tuple[FillPlan, Decimal, Decimal]] = {
        sym: (fill, Decimal("0"), Decimal("0")) for sym, fill in open_by_symbol.items()
    }
    for ts in sorted(all_ts):
        nxt: dict[str, tuple[FillPlan, Decimal, Decimal]] = {}
        for sym, (fill, mfe, mae) in still_open.items():
            bars = [b for b in candles_1m_by_symbol.get(sym, []) if to_ist(b.timestamp) == ts]
            if not bars:
                nxt[sym] = (fill, mfe, mae)
                continue
            # Skip the entry bar for stop checks (fill assumed at trigger; stop from next bar)
            if ts == fill.trigger_bar_open:
                nxt[sym] = (fill, mfe, mae)
                continue
            mfe, mae = update_excursions(
                direction=fill.direction,
                entry=fill.entry,
                quantity=fill.quantity,
                bar=bars[0],
                mfe=mfe,
                mae=mae,
            )
            closed = manage_open_to_bar(fill, bars[0], config, mfe=mfe, mae=mae)
            if closed:
                state.closed.append(closed)
                state.realized_pnl += closed.pnl
                if closed.pnl < 0:
                    state.consecutive_losses += 1
                else:
                    state.consecutive_losses = 0
            else:
                nxt[sym] = (fill, mfe, mae)
        still_open = nxt

    open_by_symbol = {sym: fill for sym, (fill, _mfe, _mae) in still_open.items()}
    path_stats = {sym: (mfe, mae) for sym, (_fill, mfe, mae) in still_open.items()}
    state.open_fills = list(open_by_symbol.values())

    # Forced exit any remainder at/after forced_exit using last available bar at/after exit
    forced = combine_ist(session_date, config.forced_exit)
    for sym, fill in list(open_by_symbol.items()):
        mfe, mae = path_stats.get(sym, (Decimal("0"), Decimal("0")))
        bars = sorted(
            (b for b in candles_1m_by_symbol.get(sym, []) if to_ist(b.timestamp) >= forced),
            key=lambda b: b.timestamp,
        )
        if not bars:
            bars = sorted(
                (b for b in candles_1m_by_symbol.get(sym, []) if to_ist(b.timestamp) <= forced),
                key=lambda b: b.timestamp,
            )
            bars = bars[-1:] if bars else []
        if not bars:
            continue
        mfe, mae = update_excursions(
            direction=fill.direction,
            entry=fill.entry,
            quantity=fill.quantity,
            bar=bars[0],
            mfe=mfe,
            mae=mae,
        )
        closed = manage_open_to_bar(fill, bars[0], config, mfe=mfe, mae=mae)
        if closed is None:
            bar = bars[0]
            exit_px = bar.close
            if fill.direction == "LONG":
                pnl = (exit_px - fill.entry) * Decimal(fill.quantity)
            else:
                pnl = (fill.entry - exit_px) * Decimal(fill.quantity)
            closed = ClosedTrade(
                fill=fill,
                exit_price=exit_px,
                exit_reason="EOD_EXIT",
                exit_time=to_ist(bar.timestamp),
                pnl=pnl,
                mfe=mfe,
                mae=mae,
            )
        state.closed.append(closed)
        state.realized_pnl += closed.pnl
        if closed.pnl < 0:
            state.consecutive_losses += 1
        else:
            state.consecutive_losses = 0
        open_by_symbol.pop(sym, None)

    # Deduplicate results: keep last decisive outcome per symbol
    by_sym: dict[str, SymbolResult] = {}
    priority = {
        "TRADED": 100,
        "RISK_INVALID": 90,
        "PORTFOLIO_RISK_LIMIT": 90,
        "DAILY_LOSS_LOCK": 90,
        "CONSECUTIVE_LOSS_LOCK": 90,
        "ORDER_REJECTED": 90,
        "BREAKOUT_NOT_TRIGGERED": 80,
        "RANKED_ARMED": 50,
        "NOT_IN_TOP_N": 40,
    }
    for row in results:
        prev = by_sym.get(row.symbol)
        if prev is None or priority.get(row.reason, 10) >= priority.get(prev.reason, 10):
            by_sym[row.symbol] = row

    return SessionReport(
        session_date=session_date,
        strategy_id=config.strategy_id,
        config_hash=config.config_hash,
        symbol_results=list(by_sym.values()),
        fills=fills,
        closed_trades=list(state.closed),
        coverage_eligible=len(screened),
        coverage_total=len(screen_inputs),
        ranked_stocks=tuple(stock_ranked),
        ranked_etfs=tuple(etf_ranked),
    )


__all__ = [
    "prior_day_atr14",
    "screen_symbol",
    "build_fill_plan",
    "update_excursions",
    "manage_open_to_bar",
    "run_session",
]
