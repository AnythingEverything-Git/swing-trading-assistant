"""Candle repository using SQLAlchemy AsyncSession.

Implements save_many, get_latest, and get_range methods.
"""
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, desc, insert, or_, and_, func
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

    async def get_range_for_instruments(
        self,
        instrument_ids: list[int],
        timeframe: str,
        start_timestamp: datetime,
        end_timestamp: datetime,
    ) -> List[CandleORM]:
        """Load candles for many instruments in one query (ordered by instrument, time)."""
        if not instrument_ids:
            return []
        stmt = (
            select(CandleORM)
            .where(CandleORM.instrument_id.in_(instrument_ids))
            .where(CandleORM.timeframe == timeframe)
            .where(CandleORM.timestamp >= start_timestamp)
            .where(CandleORM.timestamp <= end_timestamp)
            .order_by(CandleORM.instrument_id, CandleORM.timestamp)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def first_5m_volumes_by_instrument(
        self,
        instrument_ids: list[int],
        *,
        start_timestamp: datetime,
        end_timestamp: datetime,
    ) -> dict[int, dict]:
        """Sum 09:15–09:19 IST 1m volumes per instrument per IST calendar day.

        Matches ``session_service._first_5m_volumes_by_session`` exactly — only the
        opening-range minutes — without loading full-day 1m history.
        """
        from datetime import date as date_cls

        if not instrument_ids:
            return {}

        bind = self.session.get_bind()
        dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""

        if dialect == "postgresql":
            local_ts = func.timezone("Asia/Kolkata", CandleORM.timestamp)
            day_expr = func.date(local_ts)
            hour_expr = func.extract("hour", local_ts)
            minute_expr = func.extract("minute", local_ts)
            stmt = (
                select(
                    CandleORM.instrument_id,
                    day_expr.label("session_day"),
                    func.coalesce(func.sum(CandleORM.volume), 0),
                )
                .where(CandleORM.instrument_id.in_(instrument_ids))
                .where(CandleORM.timeframe == "1m")
                .where(CandleORM.timestamp >= start_timestamp)
                .where(CandleORM.timestamp < end_timestamp)
                .where(hour_expr == 9)
                .where(minute_expr >= 15)
                .where(minute_expr < 20)
                .group_by(CandleORM.instrument_id, day_expr)
            )
            result = await self.session.execute(stmt)
            out: dict[int, dict] = {}
            for instrument_id, session_day, vol in result.fetchall():
                if instrument_id is None or session_day is None:
                    continue
                day = session_day if isinstance(session_day, date_cls) else date_cls.fromisoformat(str(session_day))
                out.setdefault(int(instrument_id), {})[day] = int(vol or 0)
            return out

        # SQLite / other: load OR-window bars only via Python filter after range fetch.
        # Still accuracy-identical; used mainly in unit tests.
        rows = await self.get_range_for_instruments(instrument_ids, "1m", start_timestamp, end_timestamp)
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        out = {}
        for row in rows:
            ts = row.timestamp
            if ts.tzinfo is None:
                from datetime import timezone as tz

                ts = ts.replace(tzinfo=tz.utc)
            local = ts.astimezone(ist)
            if local.hour != 9 or not (15 <= local.minute < 20):
                continue
            bucket = out.setdefault(int(row.instrument_id), {})
            d = local.date()
            bucket[d] = bucket.get(d, 0) + int(row.volume or 0)
        return out

    async def latest_timestamp(self, timeframe: str = "1d") -> datetime | None:
        stmt = (
            select(func.max(CandleORM.timestamp))
            .where(CandleORM.timeframe == timeframe)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_instruments(self, timeframe: str = "1d") -> int:
        # DISTINCT over large candle tables is expensive; prefer distinct instrument_id
        # via a semi-join that can use (timeframe, instrument_id) if indexed.
        stmt = select(func.count()).select_from(
            select(CandleORM.instrument_id)
            .where(CandleORM.timeframe == timeframe)
            .distinct()
            .subquery()
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)
