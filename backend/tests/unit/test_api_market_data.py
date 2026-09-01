from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.schemas import MarketDataCandleResponse
from app.api.deps import get_query_service


class FakeService:
    async def get_candles(self, symbol, timeframe, start, end):
        return [
            type("C", (), {"symbol": symbol, "timeframe": timeframe, "timestamp": start, "open": Decimal("1.1"), "high": Decimal("1.2"), "low": Decimal("1.0"), "close": Decimal("1.15"), "volume": 10})
        ]


def test_get_candles_success(monkeypatch):
    app = create_app()

    async def fake_get_query_service():
        return FakeService()

    app.dependency_overrides = {get_query_service: fake_get_query_service}

    client = TestClient(app)
    start = "2020-01-01T00:00:00Z"
    end = "2020-01-01T00:00:00Z"
    resp = client.get(f"/api/v1/market-data/candles/TST?start={start}&end={end}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "TST"
    assert data[0]["open"] == "1.1" or float(data[0]["open"]) == 1.1


def test_invalid_date_range(monkeypatch):
    app = create_app()

    async def fake_get_query_service():
        return FakeService()

    app.dependency_overrides = {get_query_service: fake_get_query_service}

    client = TestClient(app)
    resp = client.get("/api/v1/market-data/candles/TST?start=2020-01-02T00:00:00Z&end=2020-01-01T00:00:00Z")
    assert resp.status_code == 400


def test_empty_result(monkeypatch):
    app = create_app()

    class EmptyService:
        async def get_candles(self, symbol, timeframe, start, end):
            return []

    async def fake_get_query_service():
        return EmptyService()

    app.dependency_overrides = {get_query_service: fake_get_query_service}
    client = TestClient(app)
    resp = client.get("/api/v1/market-data/candles/TST?start=2020-01-01T00:00:00Z&end=2020-01-01T00:00:00Z")
    assert resp.status_code == 200
    assert resp.json() == []
