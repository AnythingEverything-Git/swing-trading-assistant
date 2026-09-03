from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.schemas import MarketDataCandleResponse
from app.api.deps import get_query_service, get_upstox_provider


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


def test_quotes_endpoint_returns_live_prices_when_provider_supports_quotes():
    app = create_app()

    class FakeProvider:
        async def get_last_traded_prices(self, symbols):
            return {
                "TST": {
                    "last_price": Decimal("123.45"),
                    # Upstox quote payload exposes net_change; previous close can be derived as:
                    # prev_close = last_price - net_change
                    "raw": {"net_change": Decimal("3.45")},
                }
            }

    async def fake_provider():
        return FakeProvider()

    app.dependency_overrides[get_upstox_provider] = fake_provider
    client = TestClient(app)
    resp = client.get("/api/v1/market-data/quotes?symbols=TST,INFY")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload[0]["symbol"] == "TST"
    assert payload[0]["current_price"] == "123.45"
    assert payload[0]["current_price_change_percent"] == "2.87500"
    assert payload[1]["symbol"] == "INFY"
    assert payload[1]["current_price"] is None
