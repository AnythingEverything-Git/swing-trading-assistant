"""Breakout trigger + fill model for ORB V1."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Sequence

from app.domain.intraday.config_v1 import IntradayConfigV1, DEFAULT_CONFIG_V1
from app.domain.intraday.session_calendar import combine_ist, to_ist
from app.domain.intraday.types import Direction, OpeningRange, RankedCandidate
from app.domain.market_data import Candle


def slippage_amount(price: Decimal, tick: Decimal, config: IntradayConfigV1) -> Decimal:
    bps = price * config.slip_bps / Decimal("10000")
    return max(tick, bps)


def _snap_away(price: Decimal, tick: Decimal, direction: Direction, *, for_stop: bool) -> Decimal:
    if tick <= 0:
        return price
    # Stops: long snap down (floor), short snap up (ceil). Entries: long up, short down.
    if for_stop:
        if direction == "LONG":
            return (price / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        return (price / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    if direction == "LONG":
        return (price / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    return (price / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def find_breakout_fill(
    ranked: RankedCandidate,
    candles_1m: Sequence[Candle],
    session_date: date,
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> tuple[Decimal, Candle] | None:
    """Return (fill_price, trigger_bar) or None if no breakout before cutoff."""
    c = ranked.candidate
    orng = c.opening_range
    start = combine_ist(session_date, config.or_end)
    cutoff = combine_ist(session_date, config.entry_cutoff)
    tick = c.tick_size
    slip = slippage_amount(orng.close, tick, config)

    bars = sorted(
        (
            bar
            for bar in candles_1m
            if bar.symbol.upper() == c.symbol.upper()
            and start <= to_ist(bar.timestamp) < cutoff
        ),
        key=lambda b: b.timestamp,
    )

    for bar in bars:
        if c.direction == "LONG":
            if bar.high > orng.high:
                if bar.open > orng.high:
                    raw = max(orng.high + slip, bar.open)
                else:
                    raw = orng.high + slip
                fill = _snap_away(raw, tick, "LONG", for_stop=False)
                return fill, bar
        else:
            if bar.low < orng.low:
                if bar.open < orng.low:
                    raw = min(orng.low - slip, bar.open)
                else:
                    raw = orng.low - slip
                fill = _snap_away(raw, tick, "SHORT", for_stop=False)
                return fill, bar
    return None


def planned_stop_distance(prior_atr14: Decimal, config: IntradayConfigV1) -> Decimal:
    return prior_atr14 * config.stop_atr_mult


def stop_price(entry: Decimal, direction: Direction, stop_distance: Decimal, tick: Decimal) -> Decimal:
    raw = entry - stop_distance if direction == "LONG" else entry + stop_distance
    return _snap_away(raw, tick, direction, for_stop=True)


def validate_stop_bounds(
    *,
    entry: Decimal,
    stop_distance: Decimal,
    opening_range: OpeningRange,
    spread: Decimal,
    tick: Decimal,
    config: IntradayConfigV1,
) -> str | None:
    """Return reject detail or None if OK."""
    or_range = opening_range.high - opening_range.low
    min_stop = max(
        tick * config.stop_min_ticks,
        entry * config.stop_min_pct,
        spread * config.stop_min_spread_mult,
    )
    if stop_distance < min_stop:
        return "stop below minimum executability bound"
    if or_range > 0:
        if stop_distance < or_range * config.stop_or_min_mult:
            return "stop too tight vs opening range"
        if stop_distance > or_range * config.stop_or_max_mult:
            return "stop too wide vs opening range"
    return None


__all__ = [
    "slippage_amount",
    "find_breakout_fill",
    "planned_stop_distance",
    "stop_price",
    "validate_stop_bounds",
]
