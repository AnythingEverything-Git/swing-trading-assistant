from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Sequence

from app.domain.market_data import Candle


def _as_decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def _value_for(candle: Candle, field: str) -> Decimal:
    value = getattr(candle, field, None)
    if value is None:
        return Decimal("0")
    return _as_decimal(value)


def _ensure_positive_period(period: int, name: str) -> int:
    if period <= 0:
        raise ValueError(f"{name} period must be > 0")
    return period


def sma(candles: Sequence[Candle], period: int, field: str = "close") -> list[Decimal | None]:
    """Simple moving average over the given candle field.

    Returns a list aligned to the input candles. Leading values are None until the
    moving window has enough data for the requested period.
    """
    period = _ensure_positive_period(period, "SMA")
    values = [_value_for(c, field) for c in candles]
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out

    for idx in range(period - 1, len(values)):
        window = values[idx - period + 1 : idx + 1]
        out[idx] = sum(window, Decimal("0")) / Decimal(period)
    return out


def ema(candles: Sequence[Candle], period: int, field: str = "close") -> list[Decimal | None]:
    """Exponential moving average using Wilder-style smoothing constant.

    The first valid EMA value is the SMA of the first `period` values.
    """
    period = _ensure_positive_period(period, "EMA")
    values = [_value_for(c, field) for c in candles]
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out

    multiplier = Decimal("2") / Decimal(period + 1)
    ema_value = sum(values[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = ema_value

    for idx in range(period, len(values)):
        ema_value = (values[idx] - ema_value) * multiplier + ema_value
        out[idx] = ema_value
    return out


def _rsi_from_average(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_loss == 0:
        return Decimal("100")
    if avg_gain == 0:
        return Decimal("0")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def rsi(candles: Sequence[Candle], period: int, field: str = "close") -> list[Decimal | None]:
    """Relative strength index using Wilder's smoothing.

    The first valid RSI is produced once there are enough prior deltas to compute
    the initial gain/loss averages. Earlier entries are returned as None.
    """
    period = _ensure_positive_period(period, "RSI")
    values = [_value_for(c, field) for c in candles]
    out: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return out

    deltas = [values[idx] - values[idx - 1] for idx in range(1, len(values))]
    gains = [max(delta, Decimal("0")) for delta in deltas]
    losses = [max(-delta, Decimal("0")) for delta in deltas]

    avg_gain = sum(gains[:period], Decimal("0")) / Decimal(period)
    avg_loss = sum(losses[:period], Decimal("0")) / Decimal(period)
    out[period] = _rsi_from_average(avg_gain, avg_loss)

    for idx in range(period + 1, len(values)):
        avg_gain = ((avg_gain * Decimal(period - 1)) + gains[idx - 1]) / Decimal(period)
        avg_loss = ((avg_loss * Decimal(period - 1)) + losses[idx - 1]) / Decimal(period)
        out[idx] = _rsi_from_average(avg_gain, avg_loss)
    return out


def atr(candles: Sequence[Candle], period: int) -> list[Decimal | None]:
    """Average true range using Wilder's smoothing.

    Returns None until there are enough candles for the configured period.
    """
    period = _ensure_positive_period(period, "ATR")
    out: list[Decimal | None] = [None] * len(candles)
    if len(candles) < period:
        return out

    true_ranges: list[Decimal] = []
    for idx, candle in enumerate(candles):
        high = _value_for(candle, "high")
        low = _value_for(candle, "low")
        if idx == 0:
            true_ranges.append(high - low)
            continue
        prev_close = _value_for(candles[idx - 1], "close")
        true_ranges.append(
            max(high - low, abs(high - prev_close), abs(low - prev_close))
        )

    first_atr = sum(true_ranges[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = first_atr

    for idx in range(period, len(candles)):
        out[idx] = ((out[idx - 1] * Decimal(period - 1)) + true_ranges[idx]) / Decimal(period)
    return out


def volume_sma(candles: Sequence[Candle], period: int) -> list[Decimal | None]:
    """Simple moving average of candle volumes."""
    return sma(candles, period, field="volume")


__all__ = ["sma", "ema", "rsi", "atr", "volume_sma"]