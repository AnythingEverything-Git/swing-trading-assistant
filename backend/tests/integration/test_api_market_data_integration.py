import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import os
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.infrastructure.database import session as db_session
from app.infrastructure.database.base import Base
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository


async def _create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed(sessionmaker):
    async with sessionmaker() as sess:
        inst_repo = InstrumentRepository(sess)
        candle_repo = CandleRepository(sess)

        inst = await inst_repo.get_or_create("TST", name="Test Instrument", exchange="TEST")

        t1 = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2020, 1, 2, 0, 0, tzinfo=timezone.utc)

        candles = [
            {
                "instrument_id": inst.id,
                "timestamp": t1,
                "timeframe": "1d",
                "open": Decimal("1.00"),
                "high": Decimal("1.20"),
                "low": Decimal("0.90"),
                "close": Decimal("1.10"),
                "volume": 100,
            },
            {
                "instrument_id": inst.id,
                "timestamp": t2,
                "timeframe": "1d",
                "open": Decimal("1.10"),
                "high": Decimal("1.30"),
                "low": Decimal("1.00"),
                "close": Decimal("1.20"),
                "volume": 150,
            },
        ]

        await candle_repo.save_many(candles)
        await sess.commit()


def test_get_candles_integration():
    # Set DATABASE_URL so the app startup will initialize the engine/sessionmaker
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    app = create_app()

    # Enter TestClient to run lifespan startup
    with TestClient(app) as client:
        # After startup, sessionmaker and engine should be present
        assert hasattr(app.state, "sessionmaker")
        assert hasattr(app.state, "engine")

        # create tables and seed data using the started engine/sessionmaker
        engine = app.state.engine
        sessionmaker = app.state.sessionmaker
        asyncio.run(_create_schema(engine))
        asyncio.run(_seed(sessionmaker))

        start = "2020-01-01T00:00:00Z"
        end = "2020-01-02T00:00:00Z"
        resp = client.get(f"/api/v1/market-data/candles/TST?start={start}&end={end}&timeframe=1d")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

        first = data[0]
        assert first["symbol"] == "TST"
        assert first["timeframe"] == "1d"
        assert first["timestamp"] in ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00")
        assert Decimal(first["open"]) == Decimal("1.00")
        assert Decimal(first["high"]) == Decimal("1.20")
        assert Decimal(first["low"]) == Decimal("0.90")
        assert Decimal(first["close"]) == Decimal("1.10")
        assert int(first["volume"]) == 100


def test_get_candles_unknown_symbol_returns_empty():
    # Use the app lifespan (set DATABASE_URL so startup initializes the engine)
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    app = create_app()

    with TestClient(app) as client:
        engine = app.state.engine
        asyncio.run(_create_schema(engine))

        resp = client.get("/api/v1/market-data/candles/UNKNOWN?start=2020-01-01T00:00:00Z&end=2020-01-02T00:00:00Z&timeframe=1d")
        assert resp.status_code == 200
        assert resp.json() == []
