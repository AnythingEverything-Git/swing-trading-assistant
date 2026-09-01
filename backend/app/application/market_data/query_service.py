from __future__ import annotations

from typing import List
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


__all__ = ["MarketDataQueryService"]
