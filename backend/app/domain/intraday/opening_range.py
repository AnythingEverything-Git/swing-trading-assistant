"""Opening-range construction for ORB V1."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from app.domain.intraday.config_v1 import IntradayConfigV1, DEFAULT_CONFIG_V1
from app.domain.intraday.session_calendar import combine_ist, to_ist
from app.domain.intraday.types import Direction, OpeningRange
from app.domain.market_data import Candle


def build_opening_range(
    symbol: str,
    session_date: date,
    candles_1m: Sequence[Candle],
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> OpeningRange | None:
    """Aggregate 1m bars in [or_start, or_end) into one OR snapshot."""
    start = combine_ist(session_date, config.or_start)
    end = combine_ist(session_date, config.or_end)
    bars = [
        c
        for c in candles_1m
        if start <= to_ist(c.timestamp) < end and c.symbol.upper() == symbol.upper()
    ]
    if not bars:
        return None
    # Expect contiguous 5 bars for a full OR; allow fewer only if caller accepts DATA_STALE upstream.
    if len(bars) < 5:
        return None

    bars = sorted(bars, key=lambda c: c.timestamp)
    volume = sum(int(c.volume or 0) for c in bars)
    return OpeningRange(
        symbol=symbol.upper(),
        session_date=session_date,
        open=bars[0].open,
        high=max(c.high for c in bars),
        low=min(c.low for c in bars),
        close=bars[-1].close,
        volume=volume,
        bar_open=to_ist(bars[0].timestamp),
    )


def direction_from_or(
    opening_range: OpeningRange,
    tick_size: Decimal,
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> Direction | None:
    body = abs(opening_range.close - opening_range.open)
    doji_tol = max(tick_size, opening_range.open * config.doji_pct)
    if body <= doji_tol:
        return None
    if opening_range.close > opening_range.open:
        return "LONG"
    return "SHORT"


__all__ = ["build_opening_range", "direction_from_or"]
