"""Unit tests for repository layer using in-memory SQLite (async)."""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.database.models import InstrumentORM
from app.infrastructure.database.repositories import InstrumentRepository, CandleRepository


DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_instrument_get_or_create():
    async def _test():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            repo = InstrumentRepository(session)
            inst1 = await repo.get_or_create("ABC", name="ABC Ltd")
            assert inst1.id is not None

            inst2 = await repo.get_or_create("ABC", name="ABC Ltd")
            assert inst2.id == inst1.id
        await engine.dispose()

    asyncio.run(_test())


def test_candle_save_and_queries():
    async def _test():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            inst = InstrumentORM(symbol="TST", name="Test")
            session.add(inst)
            await session.flush()

            repo = CandleRepository(session)
            now = datetime.now(timezone.utc)
            candles = [
                {
                    "instrument_id": inst.id,
                    "timestamp": now - timedelta(days=2),
                    "timeframe": "1d",
                    "open": Decimal("100.0"),
                    "high": Decimal("110.0"),
                    "low": Decimal("95.0"),
                    "close": Decimal("105.0"),
                    "volume": 1000,
                },
                {
                    "instrument_id": inst.id,
                    "timestamp": now - timedelta(days=1),
                    "timeframe": "1d",
                    "open": Decimal("105.0"),
                    "high": Decimal("115.0"),
                    "low": Decimal("100.0"),
                    "close": Decimal("110.0"),
                    "volume": 1500,
                },
            ]

            await repo.save_many(candles)

            latest = await repo.get_latest(inst.id)
            assert latest is not None
            assert latest.close == Decimal("110.0")

            start = now - timedelta(days=3)
            end = now
            results = await repo.get_range(inst.id, "1d", start, end)
            assert len(results) == 2

            # Attempt to save a duplicate candle (same instrument/timeframe/timestamp)
            dup = candles[0].copy()
            await repo.save_many([dup])
            results_after = await repo.get_range(inst.id, "1d", start, end)
            assert len(results_after) == 2
        await engine.dispose()

    asyncio.run(_test())
