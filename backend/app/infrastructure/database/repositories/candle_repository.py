"""Candle repository using SQLAlchemy AsyncSession.

Implements save_many, get_latest, and get_range methods.
"""
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, desc, insert
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CandleORM


class CandleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_many(self, candles: List[dict]) -> None:
        """Persist multiple candles, skipping duplicates.

        Each item in `candles` should be a dict containing keys:
        instrument_id, timestamp, timeframe, open, high, low, close, volume
        """
        # Bulk insert using SQL expression; for SQLite use OR IGNORE to skip duplicates
        rows = []
        for c in candles:
            rows.append(
                {
                    "instrument_id": c["instrument_id"],
                    "timestamp": c["timestamp"],
                    "timeframe": c.get("timeframe", "1d"),
                    "open": (Decimal(c["open"]) if not isinstance(c["open"], Decimal) else c["open"]),
                    "high": (Decimal(c["high"]) if not isinstance(c["high"], Decimal) else c["high"]),
                    "low": (Decimal(c["low"]) if not isinstance(c["low"], Decimal) else c["low"]),
                    "close": (Decimal(c["close"]) if not isinstance(c["close"], Decimal) else c["close"]),
                    "volume": int(c["volume"]),
                }
            )

        if not rows:
            return

        stmt = insert(CandleORM).values(rows)

        # Try a bulk insert first. If it fails due to integrity constraints
        # (e.g., duplicates), fall back to per-row inserts and skip only
        # duplicate-key errors. This approach is portable between SQLite and
        # PostgreSQL without using dialect-specific SQL in production code.
        try:
            # Use a nested transaction (savepoint) so that if the bulk insert
            # fails we can roll back only that work without discarding other
            # changes in the session.
            async with self.session.begin_nested():
                await self.session.execute(stmt)
            await self.session.flush()
            return
        except IntegrityError:
            # nested rollback already performed; fall back to per-row inserts
            pass
        except Exception:
            # For other errors, roll back the whole session and re-raise.
            await self.session.rollback()
            raise

        # Per-row insert with duplicate-key handling performed on a fresh
        # connection. Using the engine/connection avoids transactional
        # conflicts with the AsyncSession and is portable across dialects.
        # Use the session connection to execute per-row inserts. This yields
        # an AsyncConnection appropriate for the session's bind and avoids
        # incompatibilities between sync/async engines.
        # Dialect-aware fallback to avoid creating separate engines or
        # transactional conflicts. For SQLite we can use `OR IGNORE`, for
        # PostgreSQL use `ON CONFLICT DO NOTHING`. Otherwise fall back to
        # per-row inserts using the current session.
        bind = self.session.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)

        try:
            if dialect_name == "sqlite":
                # SQLite supports OR IGNORE as a prefix.
                stmt = insert(CandleORM).prefix_with("OR IGNORE").values(rows)
                await self.session.execute(stmt)
                await self.session.flush()
                return

            if dialect_name == "postgresql":
                # Use PostgreSQL ON CONFLICT DO NOTHING.
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(CandleORM).values(rows)
                stmt = stmt.on_conflict_do_nothing(index_elements=[
                    CandleORM.instrument_id.name,
                    CandleORM.timeframe.name,
                    CandleORM.timestamp.name,
                ])
                await self.session.execute(stmt)
                await self.session.flush()
                return

            # Generic fallback: insert rows one-by-one using nested transactions
            # so that a duplicate/IntegrityError for one row does not roll
            # back the entire batch inserted so far.
            for row in rows:
                try:
                    async with self.session.begin_nested():
                        await self.session.execute(insert(CandleORM).values(row))
                except IntegrityError:
                    # duplicate or other constraint violation for this row,
                    # skip it and continue with the next. The nested transaction
                    # rollback ensures earlier inserts remain intact.
                    continue
                except Exception:
                    # re-raise unexpected errors; let caller decide how to handle
                    raise
            # make sure new rows are flushed to the DB connection
            await self.session.flush()

        finally:
            # No session expiration here; leave session state as-is to avoid
            # triggering lazy loads in unexpected contexts.
            pass

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
