from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.deps import get_strategy_evaluation_service
from app.domain.strategy.strategy import StrategyResult, TradeCandidate


class FakeStrategyService:
    def __init__(self, result=None, raise_exc=None):
        self.result = result
        self.raise_exc = raise_exc
        self.calls = []

    async def evaluate(self, symbol, timeframe, start, end):
        self.calls.append({"symbol": symbol, "timeframe": timeframe, "start": start, "end": end})
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.result is None:
            return StrategyResult(has_setup=False, status="NO_SETUP")
        return self.result


def test_strategy_evaluation_success(monkeypatch):
    app = create_app()
    candidate = TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("110.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="breakout",
    )
    service = FakeStrategyService(result=StrategyResult(has_setup=True, candidate=candidate, status="VALID_SETUP"))

    async def fake_get_strategy_evaluation_service():
        return service

    app.dependency_overrides[get_strategy_evaluation_service] = fake_get_strategy_evaluation_service
    client = TestClient(app)

    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-10T00:00:00Z",
    }

    resp = client.post("/api/v1/strategy/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_setup"] is True
    assert data["status"] == "VALID_SETUP"
    assert data["candidate"]["symbol"] == "TST"
    assert data["candidate"]["timeframe"] == "1d"
    assert data["candidate"]["direction"] == "LONG"
    assert service.calls == [{"symbol": "TST", "timeframe": "1d", "start": datetime(2024, 1, 1, tzinfo=timezone.utc), "end": datetime(2024, 1, 10, tzinfo=timezone.utc)}]


def test_strategy_evaluation_invalid_range(monkeypatch):
    app = create_app()
    service = FakeStrategyService(result=StrategyResult(has_setup=False, status="NO_SETUP"))

    async def fake_get_strategy_evaluation_service():
        return service

    app.dependency_overrides[get_strategy_evaluation_service] = fake_get_strategy_evaluation_service
    client = TestClient(app)

    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2024-01-10T00:00:00Z",
        "end": "2024-01-01T00:00:00Z",
    }

    resp = client.post("/api/v1/strategy/evaluate", json=payload)
    assert resp.status_code == 400
    assert "start must be <= end" in resp.json()["detail"]


def test_strategy_evaluation_service_error_is_not_silenced(monkeypatch):
    app = create_app()
    service = FakeStrategyService(raise_exc=RuntimeError("provider down"))

    async def fake_get_strategy_evaluation_service():
        return service

    app.dependency_overrides[get_strategy_evaluation_service] = fake_get_strategy_evaluation_service
    client = TestClient(app)

    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-10T00:00:00Z",
    }

    resp = client.post("/api/v1/strategy/evaluate", json=payload)
    assert resp.status_code == 500
    assert "provider down" in resp.json()["detail"]
