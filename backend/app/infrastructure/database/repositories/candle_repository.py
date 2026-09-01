"""Candle repository using SQLAlchemy AsyncSession.

Implements save_many, get_latest, and get_range methods.
"""
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, desc, insert, or_, and_
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CandleORM


class CandleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_many(self, candles: List[dict]) -> int:
        """Persist multiple candles, skipping duplicates.

        Each item in `candles` should be a dict containing keys:
        instrument_id, timestamp, timeframe, open, high, low, close, volume
        """
        rows = []
        seen_keys = set()
        for c in candles:
            key = (c["instrument_id"], c.get("timeframe", "1d"), c["timestamp"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(
                {
                    "instrument_id": c["instrument_id"],
                    "timestamp": c["timestamp"],
                    "timeframe": c.get("timeframe", "1d"),
                    "open": (Decimal(c["open"]) if not isinstance(c["open"], Decimal) else c["open"]),
                    "high": (Decimal(c["high"]) if not isinstance(c["high"], Decimal) else c["high"]),
                    "low": (Decimal(c["low"]) if not isinstance(c["low"], Decimal) else c["low"]),
                    "close": (Decimal(c["close"]) if not isinstance(c["close"], Decimal) else c["close"]),
                    "volume": int(c["volume"]) if c.get("volume") is not None else None,
                }
            )

        if not rows:
            return 0

        await self.session.flush()

        existing = set()
        if rows:
            predicates = []
            for r in rows:
                predicates.append(
                    and_(
                        CandleORM.instrument_id == r["instrument_id"],
                        CandleORM.timeframe == r["timeframe"],
                        CandleORM.timestamp == r["timestamp"],
                    )
                )
            if predicates:
                sel = select(CandleORM.instrument_id, CandleORM.timeframe, CandleORM.timestamp).where(or_(*predicates))
                res = await self.session.execute(sel)
                existing = {(row[0], row[1], row[2]) for row in res.fetchall()}

        pending = [r for r in rows if (r["instrument_id"], r["timeframe"], r["timestamp"]) not in existing]
        if not pending:
            return 0

        bind = self.session.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
        inserted = 0

        try:
            for row in pending:
                try:
                    if dialect_name == "sqlite":
                        stmt = insert(CandleORM).prefix_with("OR IGNORE").values(row)
                    elif dialect_name == "postgresql":
                        from sqlalchemy.dialects.postgresql import insert as pg_insert

                        stmt = pg_insert(CandleORM).values(row)
                        stmt = stmt.on_conflict_do_nothing(index_elements=[
                            CandleORM.instrument_id.name,
                            CandleORM.timeframe.name,
                            CandleORM.timestamp.name,
                        ])
                    else:
                        stmt = insert(CandleORM).values(row)

                    result = await self.session.execute(stmt)
                    rowcount = getattr(result, "rowcount", None)
                    if rowcount is not None and rowcount == 0:
                        continue
                    inserted += 1
                except IntegrityError:
                    continue
                except Exception:
                    await self.session.rollback()
                    raise

            await self.session.flush()
            return inserted
        except Exception:
            await self.session.rollback()
            raise

    async def get_latest(self, instrument_id: int, timeframe: str = "1d") -> Optional[CandleORM]:
        stmt = (
            select(CandleORM)
            .where(CandleORM.instrument_id == instrument_id)
            .where(CandleORM.timeframe == timeframe)
            .order_by(desc(CandleORM.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_range(self, instrument_id: int, timeframe: str, start_timestamp: datetime, end_timestamp: datetime) -> List[CandleORM]:
        stmt = (
            select(CandleORM)
            .where(CandleORM.instrument_id == instrument_id)
            .where(CandleORM.timeframe == timeframe)
            .where(CandleORM.timestamp >= start_timestamp)
            .where(CandleORM.timestamp <= end_timestamp)
            .order_by(CandleORM.timestamp)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
