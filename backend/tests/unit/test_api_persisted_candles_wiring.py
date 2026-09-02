"""Prove evaluate/backtest read persisted candles via MarketDataQueryService."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.deps import get_query_service, get_upstox_provider
from app.api.main import create_app
from app.domain.market_data import Candle
from app.infrastructure.database.base import Base
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository


class SpyQueryService:
    def __init__(self, candles: list[Candle] | None = None):
        self.candles = candles or []
        self.calls: list[dict] = []

    async def get_candles(self, symbol, timeframe, start, end):
        self.calls.append(
            {"symbol": symbol, "timeframe": timeframe, "start": start, "end": end}
        )
        return self.candles


async def _create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_two_candles(sessionmaker):
    async with sessionmaker() as sess:
        inst = await InstrumentRepository(sess).get_or_create("TST", exchange="TEST")
        await CandleRepository(sess).save_many(
            [
                {
                    "instrument_id": inst.id,
                    "timestamp": datetime(2020, 1, 1, tzinfo=timezone.utc),
                    "timeframe": "1d",
                    "open": Decimal("1.00"),
                    "high": Decimal("1.20"),
                    "low": Decimal("0.90"),
                    "close": Decimal("1.10"),
                    "volume": 100,
                },
                {
                    "instrument_id": inst.id,
                    "timestamp": datetime(2020, 1, 2, tzinfo=timezone.utc),
                    "timeframe": "1d",
                    "open": Decimal("1.10"),
                    "high": Decimal("1.30"),
                    "low": Decimal("1.00"),
                    "close": Decimal("1.20"),
                    "volume": 150,
                },
            ]
        )
        await sess.commit()


def _one_persisted_candle() -> Candle:
    return Candle(
        symbol="TST",
        exchange="TEST",
        instrument_id=1,
        timeframe="1d",
        timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
        open=Decimal("1.00"),
        high=Decimal("1.20"),
        low=Decimal("0.90"),
        close=Decimal("1.10"),
        volume=100,
    )


def test_evaluate_uses_persisted_query_service_not_live_provider():
    app = create_app()
    spy = SpyQueryService(candles=[_one_persisted_candle()])

    async def fake_query_service():
        return spy

    async def live_provider_must_not_run():
        raise AssertionError("live Upstox/mock provider must not supply evaluate candles")

    app.dependency_overrides[get_query_service] = fake_query_service
    app.dependency_overrides[get_upstox_provider] = live_provider_must_not_run

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/strategy/evaluate",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2020-01-01T00:00:00Z",
                "end": "2020-01-02T00:00:00Z",
            },
        )

    assert response.status_code == 200
    assert response.json()["has_setup"] is False
    assert response.json()["status"] == "NO_SETUP"
    assert len(spy.calls) == 1
    assert spy.calls[0]["symbol"] == "TST"
    assert spy.calls[0]["timeframe"] == "1d"


def test_backtest_uses_persisted_query_service_not_live_provider():
    app = create_app()
    spy = SpyQueryService(candles=[_one_persisted_candle()])

    async def fake_query_service():
        return spy

    async def live_provider_must_not_run():
        raise AssertionError("live Upstox/mock provider must not supply backtest candles")

    app.dependency_overrides[get_query_service] = fake_query_service
    app.dependency_overrides[get_upstox_provider] = live_provider_must_not_run

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2020-01-01T00:00:00Z",
                "end": "2020-01-02T00:00:00Z",
                "account_equity": "10000",
                "risk_percent": "1",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["completed_trades"] == 0
    assert body["trades"] == []
    assert len(spy.calls) == 1
    assert spy.calls[0]["symbol"] == "TST"
    assert spy.calls[0]["timeframe"] == "1d"


def test_evaluate_and_backtest_read_seeded_persisted_candles(monkeypatch):
    # Match test_health_db / test_db_lifecycle: scoped env via monkeypatch (auto-restored).
    # App lifespan creates the engine; seed through the same sessionmaker as GET candles.
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    app = create_app()

    async def live_provider_must_not_run():
        raise AssertionError("live Upstox/mock provider must not supply research candles")

    app.dependency_overrides[get_upstox_provider] = live_provider_must_not_run

    with TestClient(app) as client:
        asyncio.run(_create_schema(app.state.engine))
        asyncio.run(_seed_two_candles(app.state.sessionmaker))

        candles_resp = client.get(
            "/api/v1/market-data/candles/TST"
            "?start=2020-01-01T00:00:00Z&end=2020-01-02T00:00:00Z&timeframe=1d"
        )
        assert candles_resp.status_code == 200
        assert len(candles_resp.json()) == 2

        evaluate_resp = client.post(
            "/api/v1/strategy/evaluate",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2020-01-01T00:00:00Z",
                "end": "2020-01-02T00:00:00Z",
            },
        )
        assert evaluate_resp.status_code == 200
        assert evaluate_resp.json()["has_setup"] is False
        assert evaluate_resp.json()["status"] == "NO_SETUP"

        backtest_resp = client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2020-01-01T00:00:00Z",
                "end": "2020-01-02T00:00:00Z",
                "account_equity": "10000",
                "risk_percent": "1",
            },
        )
        assert backtest_resp.status_code == 200
        assert backtest_resp.json()["completed_trades"] == 0
        assert backtest_resp.json()["trades"] == []
