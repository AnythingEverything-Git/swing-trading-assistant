import os
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.infrastructure.database.base import Base
from app.infrastructure.database import session as db_session
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider


async def _create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_ingest_endpoint_integration(monkeypatch, tmp_path):
    # Setup DB
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    app = create_app()

    # override the provider to use Mock provider to avoid real HTTP
    async def _fake_provider_dep():
        return MockMarketDataProvider()

    from app.api.deps import get_upstox_provider
    app.dependency_overrides[get_upstox_provider] = _fake_provider_dep

    with TestClient(app) as client:
        # create schema
        engine = app.state.engine
        asyncio.run(_create_schema(engine))

        payload = {
            "symbol": "TST",
            "timeframe": "1d",
            "start": "2020-01-01T00:00:00Z",
            "end": "2020-01-03T00:00:00Z",
        }

        resp = client.post("/api/v1/market-data/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["candles_fetched"] == 3
        assert data["candles_persisted"] == 3

        # Repeating the exact same ingestion must be idempotent.
        resp2 = client.post("/api/v1/market-data/ingest", json=payload)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["candles_fetched"] == 3
        assert data2["candles_persisted"] == 0
