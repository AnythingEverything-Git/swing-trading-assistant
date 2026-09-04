"""Overview performance metrics from persisted candles."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.domain.market_data import Candle


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _return_pct(start_close: Decimal, end_close: Decimal) -> Decimal:
    if start_close == 0:
        return Decimal("0")
    return _q(((end_close - start_close) / start_close) * Decimal("100"))


@dataclass(frozen=True)
class PerformancePoint:
    label: str
    change_percent: Decimal | None


@dataclass(frozen=True)
class OverviewSnapshot:
    symbol: str
    timeframe: str
    last_close: Decimal | None
    last_volume: int | None
    performance: tuple[PerformancePoint, ...]
    high_52w: Decimal | None
    low_52w: Decimal | None
    candle_count: int


def _close_on_or_before(candles: Sequence[Candle], target: datetime) -> Decimal | None:
    chosen: Decimal | None = None
    for candle in candles:
        if candle.timestamp <= target:
            chosen = candle.close
        else:
            break
    return chosen


def build_overview_snapshot(symbol: str, timeframe: str, candles: Sequence[Candle]) -> OverviewSnapshot:
    if not candles:
        return OverviewSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            last_close=None,
            last_volume=None,
            performance=(),
            high_52w=None,
            low_52w=None,
            candle_count=0,
        )

    ordered = sorted(candles, key=lambda c: c.timestamp)
    last = ordered[-1]
    end = last.timestamp if last.timestamp.tzinfo else last.timestamp.replace(tzinfo=timezone.utc)
    windows = (
        ("1D", timedelta(days=1)),
        ("1W", timedelta(days=7)),
        ("1M", timedelta(days=30)),
        ("3M", timedelta(days=90)),
        ("1Y", timedelta(days=365)),
    )
    performance: list[PerformancePoint] = []
    for label, delta in windows:
        prior = _close_on_or_before(ordered, end - delta)
        if prior is None:
            performance.append(PerformancePoint(label=label, change_percent=None))
        else:
            performance.append(PerformancePoint(label=label, change_percent=_return_pct(prior, last.close)))

    year_ago = end - timedelta(days=365)
    year_candles = [c for c in ordered if c.timestamp >= year_ago]
    series = year_candles or ordered
    high_52w = max(c.high for c in series)
    low_52w = min(c.low for c in series)

    return OverviewSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        last_close=_q(last.close),
        last_volume=last.volume,
        performance=tuple(performance),
        high_52w=_q(high_52w),
        low_52w=_q(low_52w),
        candle_count=len(ordered),
    )


__all__ = ["OverviewSnapshot", "PerformancePoint", "build_overview_snapshot"]
