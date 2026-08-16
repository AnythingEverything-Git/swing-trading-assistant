"""Market data provider abstraction.

This module exposes a simple, runtime-checkable `MarketDataProvider`
protocol used by application code to fetch candles. Implementations live
in the `infrastructure.market_data` package. The protocol relies only on
the domain `Candle` type and avoids any vendor SDK types.
"""
from __future__ import annotations

from typing import Protocol, List, runtime_checkable
from datetime import datetime

from app.domain.market_data import Candle


@runtime_checkable
class MarketDataProvider(Protocol):
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:  # pragma: no cover - interface
        """Return candles for `symbol` in the given timeframe and range."""
