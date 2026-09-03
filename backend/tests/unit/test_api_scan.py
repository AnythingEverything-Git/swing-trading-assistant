"""Focused API tests for POST /api/v1/scan/opportunities."""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.deps import get_opportunity_scan_service, get_strategy_evaluation_service, get_upstox_provider
from app.api.main import create_app
from app.application.scan.opportunity_scan_service import (
    EligibleOpportunity,
    OpportunityScanResult,
)
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate
from app.domain.universe import StockUniverse
from app.infrastructure.universe import Nifty500Universe


START = datetime(2025, 12, 7, tzinfo=timezone.utc)
END = datetime(2026, 9, 3, tzinfo=timezone.utc)


def _evidence() -> StrategyEvidence:
    return StrategyEvidence(
        resistance=Decimal("101.50"),
        breakout_candle_index=19,
        breakout_candle_time=datetime(2024, 1, 20, tzinfo=timezone.utc),
        retest_candle_index=20,
        retest_candle_time=datetime(2024, 1, 21, tzinfo=timezone.utc),
        confirmation_candle_index=21,
        confirmation_candle_time=datetime(2024, 1, 22, tzinfo=timezone.utc),
        atr_value=Decimal("2.50"),
        volume_sma_value=Decimal("1200"),
        breakout_volume=2000,
        retest_low=Decimal("99.00"),
        confirmation_volume=2200,
        decision="valid breakout -> retest -> confirmation",
    )


def _candidate(symbol: str = "INFY") -> TradeCandidate:
    return TradeCandidate(
        symbol=symbol,
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("104.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="BreakoutRetestConfirmation",
    )


class FakeOpportunityScanService:
    def __init__(self, result=None, raise_exc=None):
        self.result = result
        self.raise_exc = raise_exc
        self.calls = []

    async def scan_universe(self, universe: StockUniverse, timeframe, start, end):
        self.calls.append(
            {
                "universe": universe,
                "universe_type": type(universe),
                "timeframe": timeframe,
                "start": start,
                "end": end,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.result


def _success_result() -> OpportunityScanResult:
    return OpportunityScanResult(
        symbols_scanned=5,
        eligible_count=1,
        opportunities=(
            EligibleOpportunity(
                symbol="INFY",
                candidate=_candidate("INFY"),
                evidence=_evidence(),
            ),
        ),
    )


def test_scan_opportunities_success_maps_candidate_and_evidence():
    app = create_app()
    service = FakeOpportunityScanService(result=_success_result())
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["universe_name"] == "NIFTY_500"
    assert data["universe_version"]
    assert data["timeframe"] == "1d"
    assert data["symbols_scanned"] == 5
    assert data["eligible_count"] == 1
    assert data["no_setup_count"] == 4
    assert len(data["opportunities"]) == 1

    opp = data["opportunities"][0]
    assert opp["symbol"] == "INFY"
    assert opp["candidate"]["symbol"] == "INFY"
    assert opp["candidate"]["direction"] == "LONG"
    assert opp["candidate"]["entry_price"] == "100.00"
    assert opp["candidate"]["stop_loss"] == "98.00"
    assert opp["candidate"]["target"] == "104.00"
    assert opp["candidate"]["setup_name"] == "BreakoutRetestConfirmation"
    assert opp["evidence"]["resistance"] == "101.50"
    assert opp["evidence"]["breakout_candle_index"] == 19
    assert opp["evidence"]["confirmation_candle_index"] == 21
    assert opp["evidence"]["decision"] == "valid breakout -> retest -> confirmation"


def test_scan_opportunities_no_setup_count_is_scanned_minus_eligible():
    app = create_app()
    result = OpportunityScanResult(symbols_scanned=10, eligible_count=3, opportunities=())
    service = FakeOpportunityScanService(result=result)
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["symbols_scanned"] == 10
    assert data["eligible_count"] == 3
    assert data["no_setup_count"] == 7
    assert data["opportunities"] == []


def test_scan_opportunities_invalid_range_returns_400():
    app = create_app()
    service = FakeOpportunityScanService(result=_success_result())
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1d",
            "start": "2026-09-03T00:00:00Z",
            "end": "2025-12-07T00:00:00Z",
        },
    )

    assert resp.status_code == 400
    assert "start must be <= end" in resp.json()["detail"]
    assert service.calls == []


def test_scan_opportunities_unsupported_timeframe_returns_400():
    app = create_app()
    service = FakeOpportunityScanService(result=_success_result())
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1h",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 400
    assert "1d" in resp.json()["detail"]
    assert service.calls == []


def test_scan_opportunities_value_error_returns_400():
    app = create_app()
    service = FakeOpportunityScanService(raise_exc=ValueError("candles must contain at least one value"))
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 400
    assert "candles must contain at least one value" in resp.json()["detail"]


def test_scan_opportunities_unexpected_error_returns_500():
    app = create_app()
    service = FakeOpportunityScanService(raise_exc=RuntimeError("db unavailable"))
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 500
    assert "db unavailable" in resp.json()["detail"]


def test_scan_opportunities_forwards_timeframe_start_end_and_nifty500_universe():
    app = create_app()
    service = FakeOpportunityScanService(result=_success_result())
    app.dependency_overrides[get_opportunity_scan_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 200
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["timeframe"] == "1d"
    assert call["start"] == START
    assert call["end"] == END
    assert call["universe_type"] is Nifty500Universe
    assert isinstance(call["universe"], Nifty500Universe)
    assert call["universe"].get_snapshot().name == "NIFTY_500"


def test_scan_dep_composes_from_strategy_evaluation_not_upstox_or_demo():
    """Wiring check: opportunity scan depends on strategy evaluation, not Upstox/Demo."""
    from app.api import deps

    params = inspect.signature(deps.get_opportunity_scan_service).parameters
    evaluation_param = params["evaluation_service"]
    assert evaluation_param.default.dependency is get_strategy_evaluation_service

    # Strategy evaluation is built from MarketDataQueryService (persisted candles).
    strategy_params = inspect.signature(get_strategy_evaluation_service).parameters
    assert "query_service" in strategy_params

    # Upstox is a separate dependency and is not an input to the scan service.
    assert "provider" not in params
    assert "upstox" not in params
    upstox_sig = inspect.signature(get_upstox_provider)
    assert upstox_sig.parameters  # exists as its own dep for ingest only
