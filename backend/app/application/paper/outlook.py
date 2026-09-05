"""Market-based ETA outlook for open paper trades.

Uses recent daily candles: ATR, average true range, and directional drift
toward the profit goal to estimate trading days until target.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from typing import Literal, Sequence

from app.domain.market_data import Candle
from app.domain.market_data.indicators import atr
from app.domain.paper import Direction

Confidence = Literal["low", "medium", "high"]

_METHOD_LABELS = {
    "drift_atr_blend": "recent move with ATR check",
    "recent_drift": "recent price drift",
    "atr_capture": "typical ATR pace",
    "avg_range": "average daily range",
    "target_reached": "profit goal already reached",
    "insufficient_data": "not enough candle history",
}


def _money_2(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{value.quantize(Decimal('0.01'))}"


@dataclass(frozen=True)
class TradeOutlook:
    trade_id: int
    symbol: str
    direction: Direction
    mark: Decimal
    entry: Decimal
    target: Decimal
    stop: Decimal
    distance_to_target: Decimal
    distance_to_stop: Decimal
    progress_pct: Decimal
    atr14: Decimal | None
    avg_daily_range: Decimal | None
    drift_per_day: Decimal | None
    pace_per_day: Decimal | None
    estimated_trading_days: Decimal | None
    estimated_reach_at: datetime | None
    confidence: Confidence
    method: str
    summary: str


def _as_dec(value: object) -> Decimal:
    return Decimal(str(value))


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def build_trade_outlook(
    *,
    trade_id: int,
    symbol: str,
    direction: Direction,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    mark: Decimal,
    candles: Sequence[Candle],
    now: datetime | None = None,
    lookback: int = 15,
) -> TradeOutlook:
    stamp = now or datetime.now(timezone.utc)
    entry_d = _as_dec(entry)
    stop_d = _as_dec(stop)
    target_d = _as_dec(target)
    mark_d = _as_dec(mark)

    if direction == "LONG":
        distance_to_target = target_d - mark_d
        distance_to_stop = mark_d - stop_d
        path = target_d - entry_d
        progress = ((mark_d - entry_d) / path * Decimal("100")) if path > 0 else Decimal("0")
    else:
        distance_to_target = mark_d - target_d
        distance_to_stop = stop_d - mark_d
        path = entry_d - target_d
        progress = ((entry_d - mark_d) / path * Decimal("100")) if path > 0 else Decimal("0")

    progress = max(Decimal("0"), min(Decimal("100"), progress))

    atr_values = atr(list(candles), 14) if len(candles) >= 14 else []
    atr14_raw = next((value for value in reversed(atr_values) if value is not None), None)
    atr14 = atr14_raw.quantize(Decimal("0.01")) if atr14_raw is not None else None

    ranges: list[Decimal] = []
    for candle in candles[-lookback:]:
        ranges.append(_as_dec(candle.high) - _as_dec(candle.low))
    avg_raw = _mean(ranges)
    avg_daily_range = avg_raw.quantize(Decimal("0.01")) if avg_raw is not None else None

    closes = [_as_dec(c.close) for c in candles]
    drift_per_day: Decimal | None = None
    if len(closes) >= lookback + 1:
        window = closes[-(lookback + 1) :]
        raw_drift = (window[-1] - window[0]) / Decimal(lookback)
        # Positive = moving toward the profit goal
        drift_per_day = raw_drift if direction == "LONG" else -raw_drift

    atr_pace = (atr14 * Decimal("0.40")) if atr14 and atr14 > 0 else None
    range_pace = (avg_daily_range * Decimal("0.35")) if avg_daily_range and avg_daily_range > 0 else None

    pace: Decimal | None = None
    method = "insufficient_data"
    confidence: Confidence = "low"

    if drift_per_day is not None and drift_per_day > 0:
        pace = drift_per_day
        method = "recent_drift"
        confidence = "high" if len(closes) >= lookback + 1 else "medium"
        # Blend a bit of ATR so one hot streak does not understate time
        if atr_pace is not None:
            pace = (pace * Decimal("0.7")) + (atr_pace * Decimal("0.3"))
            method = "drift_atr_blend"
    elif atr_pace is not None:
        pace = atr_pace
        method = "atr_capture"
        confidence = "medium"
    elif range_pace is not None:
        pace = range_pace
        method = "avg_range"
        confidence = "low"

    estimated_trading_days: Decimal | None = None
    estimated_reach_at: datetime | None = None

    if distance_to_target <= 0:
        estimated_trading_days = Decimal("0")
        estimated_reach_at = stamp
        summary = (
            f"{symbol}: live price has already reached (or passed) the profit goal on this mark. "
            "Consider taking profit on a real trade if still open."
        )
        confidence = "high"
        method = "target_reached"
    elif pace is not None and pace > 0:
        days = distance_to_target / pace
        # Clamp to a sensible swing window
        days = max(Decimal("0.5"), min(Decimal("60"), days))
        estimated_trading_days = days.quantize(Decimal("0.1"))
        # Map trading days ≈ calendar days * 7/5
        calendar_days = int((days * Decimal("7") / Decimal("5")).to_integral_value(rounding=ROUND_CEILING))
        estimated_reach_at = stamp + timedelta(days=max(1, calendar_days))
        day_label = f"{estimated_trading_days} trading day(s)"
        conf_label = {"low": "rough", "medium": "moderate", "high": "strong"}[confidence]
        method_label = _METHOD_LABELS.get(method, method.replace("_", " "))
        summary = (
            f"{symbol}: about {day_label} to the profit goal at the current pace "
            f"({method_label}, {conf_label} confidence). "
            f"About ₹{_money_2(distance_to_target)} left to the goal; "
            f"14-day ATR ≈ ₹{_money_2(atr14)}."
        )
    else:
        summary = (
            f"{symbol}: not enough recent candle history to estimate when the profit goal may be reached. "
            "Timer still tracks how long the practice trade has been open."
        )

    return TradeOutlook(
        trade_id=trade_id,
        symbol=symbol,
        direction=direction,
        mark=mark_d,
        entry=entry_d,
        target=target_d,
        stop=stop_d,
        distance_to_target=distance_to_target,
        distance_to_stop=distance_to_stop,
        progress_pct=progress.quantize(Decimal("0.1")),
        atr14=atr14,
        avg_daily_range=avg_daily_range,
        drift_per_day=drift_per_day,
        pace_per_day=pace,
        estimated_trading_days=estimated_trading_days,
        estimated_reach_at=estimated_reach_at,
        confidence=confidence,
        method=method,
        summary=summary,
    )


__all__ = ["TradeOutlook", "build_trade_outlook"]
