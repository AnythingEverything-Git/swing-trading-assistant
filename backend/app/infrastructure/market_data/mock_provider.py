from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from app.domain.market_data import Candle
from app.domain.market_data.provider import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    """Deterministic in-memory market-data provider for tests.

    - If `candles` is provided, it will be used verbatim.
    - Otherwise a deterministic sequence is generated for the requested
      symbol/timeframe/date range.
    """

    def __init__(self, candles: Optional[List[Candle]] = None):
        self._candles = list(candles) if candles is not None else None

    @staticmethod
    def _parse_timeframe(tf: str) -> timedelta:
        # Basic timeframe parsing: supports e.g. '1d', '4h', '30m'.
        if tf.endswith("d"):
            return timedelta(days=int(tf[:-1]))
        if tf.endswith("h"):
            return timedelta(hours=int(tf[:-1]))
        if tf.endswith("m"):
            return timedelta(minutes=int(tf[:-1]))
        # fallback to 1 day
        return timedelta(days=1)

    @staticmethod
    def _generate_for_range(symbol: str, timeframe: str, start: datetime, end: datetime) -> List[Candle]:
        step = MockMarketDataProvider._parse_timeframe(timeframe)
        # deterministic base price derived from symbol
        base = Decimal(100 + (sum(ord(c) for c in symbol) % 50))
        out: List[Candle] = []
        idx = 0
        cur = start
        while cur <= end:
            # create small deterministic variation
            open_p = base + Decimal(idx % 5)
            close_p = open_p + Decimal(((idx * 3) % 7) - 3)
            high_p = max(open_p, close_p) + Decimal(2)
            low_p = min(open_p, close_p) - Decimal(2)
            vol = 1000 + (idx * 10)
            out.append(
                Candle(
                    symbol=symbol,
                    exchange="TEST",
                    instrument_id=None,
                    timeframe=timeframe,
                    timestamp=cur,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=vol,
                )
            )
            idx += 1
            cur = cur + step
        return out

    async def get_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[Candle]:
        if self._candles is not None:
            # filter provided candles deterministically
            return [
                c
                for c in self._candles
                if c.symbol == symbol
                and c.timeframe == timeframe
                and start <= c.timestamp <= end
            ]

        # else generate
        return MockMarketDataProvider._generate_for_range(symbol, timeframe, start, end)
