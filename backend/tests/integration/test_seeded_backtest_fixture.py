"""Integration coverage for deterministic backtest fixture seeding."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.infrastructure.database.base import Base
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.market_data.deterministic_setup_series import (
    build_two_independent_setup_series,
)
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider


async def _create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_fixture(sessionmaker) -> tuple[int, int]:
    series = build_two_independent_setup_series()
    async with sessionmaker() as sess:
        svc = MarketDataIngestionService(
            MockMarketDataProvider(candles=series),
            InstrumentRepository(sess),
            CandleRepository(sess),
        )
        fetched, persisted = await svc.ingest(
            "TST",
            "1d",
            series[0].timestamp,
            series[-1].timestamp,
        )
        await sess.commit()
    return fetched, persisted


def _fixture_range_iso() -> tuple[str, str, list]:
    series = build_two_independent_setup_series()
    start = series[0].timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    end = series[-1].timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return start, end, series


def test_seeded_fixture_is_retrievable_via_candles_api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    app = create_app()
    start, end, series = _fixture_range_iso()

    with TestClient(app) as client:
        asyncio.run(_create_schema(app.state.engine))
        fetched, persisted = asyncio.run(_seed_fixture(app.state.sessionmaker))
        assert fetched == len(series)
        assert persisted == len(series)

        response = client.get(
            f"/api/v1/market-data/candles/TST?start={start}&end={end}&timeframe=1d"
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(series)
    assert body[0]["symbol"] == "TST"
    assert body[0]["timeframe"] == "1d"
    assert Decimal(str(body[0]["close"])) == series[0].close
    assert Decimal(str(body[-1]["close"])) == series[-1].close
    assert Decimal(str(body[21]["close"])) == Decimal("101.2")
    assert Decimal(str(body[41]["close"])) == Decimal("108.0")


def test_seeded_fixture_backtest_produces_two_real_trades(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    app = create_app()
    start, end, series = _fixture_range_iso()

    with TestClient(app) as client:
        asyncio.run(_create_schema(app.state.engine))
        asyncio.run(_seed_fixture(app.state.sessionmaker))

        response = client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": start,
                "end": end,
                "account_equity": "10000",
                "risk_percent": "1",
                "slippage_per_share": "0",
                "cost_per_trade": "0",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["completed_trades"] == 2
    assert len(body["trades"]) == 2
    assert Decimal(str(body["trades"][0]["entry_price"])) == Decimal("101.2")
    assert Decimal(str(body["trades"][1]["entry_price"])) == Decimal("108.0")
    assert len(series) == 43
