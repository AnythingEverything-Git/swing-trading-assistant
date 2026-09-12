from __future__ import annotations

from typing import Dict, List, Sequence
from datetime import datetime, date as date_cls

from app.domain.market_data import Candle as DomainCandle
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository

_DEFAULT_EXCHANGE = "NSE"


def _instrument_exchange(inst: object) -> str:
    """Domain candles require a non-empty exchange; older rows may have NULL."""
    raw = getattr(inst, "exchange", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _DEFAULT_EXCHANGE


class MarketDataQueryService:
    def __init__(self, instrument_repo: InstrumentRepository, candle_repo: CandleRepository) -> None:
        self.instrument_repo = instrument_repo
        self.candle_repo = candle_repo

    async def get_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[DomainCandle]:
        inst = await self.instrument_repo.get_by_symbol(symbol)
        if not inst:
            return []

        rows = await self.candle_repo.get_range(inst.id, timeframe, start, end)
        exchange = _instrument_exchange(inst)
        out: List[DomainCandle] = []
        for r in rows:
            out.append(
                DomainCandle(
                    symbol=symbol,
                    exchange=exchange,
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
        *,
        chunk_size: int = 100,
    ) -> Dict[str, List[DomainCandle]]:
        """Batch-load candles for many symbols (chunked IN queries; identical rows)."""
        if not symbols:
            return {}

        instruments = await self.instrument_repo.get_by_symbols(list(symbols))
        by_id = {inst.id: inst for inst in instruments}
        if not by_id:
            return {symbol: [] for symbol in symbols}

        ids = list(by_id.keys())
        rows = []
        size = max(1, int(chunk_size))
        for i in range(0, len(ids), size):
            chunk = ids[i : i + size]
            rows.extend(await self.candle_repo.get_range_for_instruments(chunk, timeframe, start, end))

        grouped: Dict[str, List[DomainCandle]] = {symbol: [] for symbol in symbols}
        for inst in instruments:
            grouped.setdefault(inst.symbol, [])

        for row in rows:
            inst = by_id.get(row.instrument_id)
            if inst is None:
                continue
            grouped.setdefault(inst.symbol, []).append(
                DomainCandle(
                    symbol=inst.symbol,
                    exchange=_instrument_exchange(inst),
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

    async def get_first_5m_volumes_for_symbols(
        self,
        symbols: Sequence[str],
        *,
        hist_start: datetime,
        session_start: datetime,
    ) -> Dict[str, dict[date_cls, int]]:
        """Per-symbol IST date -> first-5m volume (same definition as hist 1m scan)."""
        if not symbols:
            return {}
        instruments = await self.instrument_repo.get_by_symbols(list(symbols))
        by_id = {inst.id: inst for inst in instruments}
        if not by_id:
            return {s: {} for s in symbols}

        ids = list(by_id.keys())
        aggregated: dict[int, dict[date_cls, int]] = {}
        chunk_size = 100
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i : i + chunk_size]
            part = await self.candle_repo.first_5m_volumes_by_instrument(
                chunk,
                start_timestamp=hist_start,
                end_timestamp=session_start,
            )
            for iid, day_map in part.items():
                bucket = aggregated.setdefault(int(iid), {})
                for d, vol in day_map.items():
                    day = d if isinstance(d, date_cls) else date_cls.fromisoformat(str(d))
                    bucket[day] = int(vol)

        out: Dict[str, dict[date_cls, int]] = {s: {} for s in symbols}
        for iid, day_map in aggregated.items():
            inst = by_id.get(iid)
            if inst is None:
                continue
            out[inst.symbol] = dict(day_map)
        return out


__all__ = ["MarketDataQueryService"]
