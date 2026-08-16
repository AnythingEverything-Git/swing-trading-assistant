import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.market_data.factory import UpstoxProviderFactory
from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    async def json(self):
        return self._payload


class FakeClient:
    def __init__(self, timeout=None):
        self._resp = None
        self.closed = False

    async def get(self, url, headers=None, timeout=None):
        # return pre-set response
        return self._resp

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_integration_ingest_with_wired_upstox_provider():
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    # Prepare fake Upstox V3 payload (3 daily candles)
    ts0 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    ts1 = int(datetime(2020, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)
    ts2 = int(datetime(2020, 1, 3, tzinfo=timezone.utc).timestamp() * 1000)
    candles = [
        [ts0, "100", "110", "90", "105", 10, 0],
        [ts1, "105", "115", "95", "110", 20, 0],
        [ts2, "110", "120", "100", "115", 30, 0],
    ]
    payload = {"status": "success", "data": {"candles": candles}}

    # Setup factory with FakeClient class and instrument mapping
    fake_client = FakeClient()
    fake_client._resp = FakeResp(200, payload)

    def client_cls(timeout=None):
        return fake_client

    factory = UpstoxProviderFactory(client_cls=client_cls, instrument_key_map={"TST": "IK:TST"})
    # pass both base_url and access_token (empty string) so tests don't load Settings()
    provider = await factory.startup(base_url="https://api.test", access_token="")

    # Use real repositories
    async with async_session() as session:
        inst_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        svc = MarketDataIngestionService(provider, inst_repo, candle_repo)

        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = datetime(2020, 1, 3, tzinfo=timezone.utc)

        count = await svc.ingest("TST", "1d", start, end)
        assert count == 3

        inst = await inst_repo.get_by_symbol("TST")
        assert inst is not None

        results = await candle_repo.get_range(inst.id, "1d", start, end)
        assert len(results) == 3

    await factory.shutdown()
    await engine.dispose()
