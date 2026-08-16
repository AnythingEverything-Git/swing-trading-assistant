"""Market data provider abstraction.

Protocol that concrete infra adapters (e.g., Upstox) must implement.
Domain layer depends on this protocol only.
"""
from typing import Protocol, List
from ..entities.instrument import Instrument
from ..entities.candle import Candle
from datetime import datetime


class MarketDataProvider(Protocol):
    def get_universe(self) -> List[Instrument]:  # pragma: no cover - interface
        """Return a list of instruments representing the trading universe."""

    def get_historical_candles(self, symbol: str, start: datetime, end: datetime) -> List[Candle]:  # pragma: no cover - interface
        """Return daily candles for the given symbol between start and end."""
