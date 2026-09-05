from __future__ import annotations

from typing import Dict, List, Sequence
from datetime import datetime

from app.domain.market_data import Candle as DomainCandle
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository


class MarketDataQueryService:
    def __init__(self, instrument_repo: InstrumentRepository, candle_repo: CandleRepository) -> None:
        self.instrument_repo = instrument_repo
        self.candle_repo = candle_repo

    async def get_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[DomainCandle]:
        inst = await self.instrument_repo.get_by_symbol(symbol)
        if not inst:
            return []

        rows = await self.candle_repo.get_range(inst.id, timeframe, start, end)
        out: List[DomainCandle] = []
        for r in rows:
            out.append(
                DomainCandle(
                    symbol=symbol,
                    exchange=getattr(inst, "exchange", None),
                    instrument_id=inst.id,
                    timeframe=r.timeframe,
                    timestamp=r.timestamp,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    volume=r.volume,
                )
            )
        return out

    async def get_candles_for_symbols(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[DomainCandle]]:
        """Batch-load candles for many symbols (2 DB queries instead of 2N)."""
        if not symbols:
            return {}

        instruments = await self.instrument_repo.get_by_symbols(list(symbols))
        by_id = {inst.id: inst for inst in instruments}
        if not by_id:
            return {symbol: [] for symbol in symbols}

        rows = await self.candle_repo.get_range_for_instruments(
            list(by_id.keys()), timeframe, start, end
        )
        grouped: Dict[str, List[DomainCandle]] = {symbol: [] for symbol in symbols}
        # Also ensure known instruments map even if not in requested order duplicates
        for inst in instruments:
            grouped.setdefault(inst.symbol, [])

        for row in rows:
            inst = by_id.get(row.instrument_id)
            if inst is None:
                continue
            grouped.setdefault(inst.symbol, []).append(
                DomainCandle(
                    symbol=inst.symbol,
                    exchange=getattr(inst, "exchange", None),
                    instrument_id=inst.id,
                    timeframe=row.timeframe,
                    timestamp=row.timestamp,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                )
            )
        return grouped


__all__ = ["MarketDataQueryService"]
