"""Market data ingestion application service.

Coordinates fetching candles from a MarketDataProvider and persisting
them via the repository layer. The service does not manage transactions
or database engines; that responsibility remains with the caller.
"""
from __future__ import annotations

from typing import Sequence
from datetime import datetime

from app.domain.market_data.provider import MarketDataProvider
from app.domain.market_data import Candle as DomainCandle
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository


class MarketDataIngestionService:
    def __init__(self, provider: MarketDataProvider, instrument_repo: InstrumentRepository, candle_repo: CandleRepository) -> None:
        self.provider = provider
        self.instrument_repo = instrument_repo
        self.candle_repo = candle_repo

    async def ingest(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> tuple[int, int]:
        """Fetch candles from provider and persist them.

        Returns (fetched_count, persisted_count).
        Raises ValueError for invalid ranges. Does not swallow provider or
        repository exceptions.
        """
        if start is None or end is None:
            raise ValueError("start and end must be provided")
        if start > end:
            raise ValueError("start must be <= end")

        candles = await self.provider.get_candles(symbol, timeframe, start, end)
        if not candles:
            return 0, 0

        # Ensure instrument exists (get or create). Use the exchange from
        # the first candle if available.
        first = candles[0]
        exchange = getattr(first, "exchange", None)

        inst = await self.instrument_repo.get_or_create(symbol=symbol, exchange=exchange)

        # Map domain candles to persistence dicts expected by CandleRepository.save_many
        rows = []
        for c in candles:
            if not isinstance(c, DomainCandle):
                # allow provider implementations that return compatible types
                # but keep a minimal runtime check
                raise TypeError("Provider returned non-Candle items")
            rows.append(
                {
                    "instrument_id": inst.id,
                    "timestamp": c.timestamp,
                    "timeframe": c.timeframe,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
            )

        fetched_count = len(rows)
        persisted_count = await self.candle_repo.save_many(rows)
        return fetched_count, persisted_count
