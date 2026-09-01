import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider
from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService


@pytest.mark.asyncio
async def test_integration_ingest_creates_instrument_and_persists_candles():
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    # Prepare provider with 3 deterministic daily candles
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    provider = MockMarketDataProvider()

    async with async_session() as session:
        inst_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        svc = MarketDataIngestionService(provider, inst_repo, candle_repo)

        # First ingestion
        fetched_count, persisted_count = await svc.ingest("TST", "1d", start, end)
        assert fetched_count == 3
        assert persisted_count == 3

        # Instrument should exist
        inst = await inst_repo.get_by_symbol("TST")
        assert inst is not None

        # Candles persisted
        results = await candle_repo.get_range(inst.id, "1d", start, end)
        assert len(results) == 3

        latest = await candle_repo.get_latest(inst.id)
        assert latest is not None

        # Re-ingest same candles — should not create duplicates
        fetched_count2, persisted_count2 = await svc.ingest("TST", "1d", start, end)
        assert fetched_count2 == 3
        assert persisted_count2 == 0

        results_after = await candle_repo.get_range(inst.id, "1d", start, end)
        assert len(results_after) == 3

        # Partial overlap: one existing candle + one new candle.
        partial_start = start + timedelta(days=2)
        partial_end = start + timedelta(days=3)
        fetched_count3, persisted_count3 = await svc.ingest("TST", "1d", partial_start, partial_end)
        assert fetched_count3 == 2
        assert persisted_count3 == 1

        final_results = await candle_repo.get_range(inst.id, "1d", start, partial_end)
        assert len(final_results) == 4

    await engine.dispose()
