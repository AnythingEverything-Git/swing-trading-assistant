"""Focused API tests for POST /api/v1/scan/opportunities."""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.deps import (
    get_db,
    get_strategy_evaluation_service,
    get_universe_scan_report_service,
    get_upstox_provider,
)
from app.api.main import create_app
from app.application.scan.opportunity_scan_service import EligibleOpportunity
from app.application.scan.universe_scan_report_service import (
    SymbolScanIssue,
    UniverseScanReport,
)
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate
from app.domain.universe import StockUniverse
from app.infrastructure.universe import Nifty500Universe, get_universe
from app.infrastructure.universe.static_file_universe import Nifty50Universe


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


class FakeUniverseScanReportService:
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


class FakeDbSession:
    def __init__(self):
        self.added = []

    def add(self, row):
        row.id = 7
        self.added.append(row)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _override_get_db():
    yield FakeDbSession()


def _override_scan_deps(app, service: FakeUniverseScanReportService) -> None:
    app.dependency_overrides[get_universe_scan_report_service] = lambda: service
    app.dependency_overrides[get_db] = _override_get_db


def _success_result() -> UniverseScanReport:
    return UniverseScanReport(
        symbols_scanned=5,
        eligible_count=1,
        no_setup_count=3,
        unavailable_count=1,
        error_count=0,
        opportunities=(
            EligibleOpportunity(
                symbol="INFY",
                candidate=_candidate("INFY"),
                evidence=_evidence(),
            ),
        ),
        issues=(
            SymbolScanIssue(
                symbol="MISS",
                status="UNAVAILABLE",
                detail="candles must contain at least one value",
            ),
        ),
    )


def test_scan_opportunities_success_maps_candidate_and_evidence():
    app = create_app()
    service = FakeUniverseScanReportService(result=_success_result())
    _override_scan_deps(app, service)
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
    assert data["no_setup_count"] == 3
    assert data["unavailable_count"] == 1
    assert data["error_count"] == 0
    assert len(data["opportunities"]) == 1
    assert data["issues"][0]["symbol"] == "MISS"
    assert data["issues"][0]["status"] == "UNAVAILABLE"
    assert data["scan_run_id"] == 7

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
    assert data["data_source"] in {"demo", "upstox"}
    assert data["forming_count"] == 0
    assert data["top"][0]["symbol"] == "INFY"
    assert data["top"][0]["narrative"]
    assert data["top"][0]["quality_score"] is not None
    assert data["alert_preview"]


def test_scan_opportunities_no_setup_count_is_reported_directly():
    app = create_app()
    result = UniverseScanReport(
        symbols_scanned=10,
        eligible_count=3,
        no_setup_count=7,
        unavailable_count=0,
        error_count=0,
        opportunities=(),
        issues=(),
    )
    service = FakeUniverseScanReportService(result=result)
    _override_scan_deps(app, service)
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
    assert data["unavailable_count"] == 0
    assert data["error_count"] == 0
    assert data["opportunities"] == []
    assert data["issues"] == []
    assert data["scan_run_id"] == 7


def test_scan_opportunities_invalid_range_returns_400():
    app = create_app()
    service = FakeUniverseScanReportService(result=_success_result())
    _override_scan_deps(app, service)
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
    service = FakeUniverseScanReportService(result=_success_result())
    _override_scan_deps(app, service)
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
    service = FakeUniverseScanReportService(raise_exc=ValueError("invalid range"))
    _override_scan_deps(app, service)
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
    assert "invalid range" in resp.json()["detail"]


def test_scan_opportunities_unexpected_error_returns_500():
    app = create_app()
    service = FakeUniverseScanReportService(raise_exc=RuntimeError("db unavailable"))
    _override_scan_deps(app, service)
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
    service = FakeUniverseScanReportService(result=_success_result())
    _override_scan_deps(app, service)
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
    assert call["universe"].get_snapshot().name == "NIFTY_500"
    assert isinstance(call["universe"], Nifty500Universe) or call["universe"].get_snapshot().name == "NIFTY_500"


def test_scan_opportunities_accepts_nifty_50_universe():
    app = create_app()
    service = FakeUniverseScanReportService(result=_success_result())
    _override_scan_deps(app, service)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "universe": "NIFTY_50",
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 200
    assert service.calls[0]["universe"].get_snapshot().name == "NIFTY_50"
    assert len(service.calls[0]["universe"].get_snapshot().symbols) == 50
    assert resp.json()["universe_name"] == "NIFTY_50"


def test_scan_opportunities_rejects_unknown_universe():
    app = create_app()
    service = FakeUniverseScanReportService(result=_success_result())
    _override_scan_deps(app, service)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/scan/opportunities",
        json={
            "universe": "NIFTY_999",
            "timeframe": "1d",
            "start": "2025-12-07T00:00:00Z",
            "end": "2026-09-03T00:00:00Z",
        },
    )

    assert resp.status_code == 400
    assert "universe" in resp.json()["detail"].lower()
    assert service.calls == []


def test_get_universe_registry_nested_membership():
    nifty50 = get_universe("NIFTY_50").get_snapshot()
    nifty100 = get_universe("NIFTY_100").get_snapshot()
    nifty200 = get_universe("NIFTY_200").get_snapshot()
    nifty500 = get_universe("NIFTY_500").get_snapshot()
    assert len(nifty50.symbols) == 50
    assert len(nifty100.symbols) == 100
    assert len(nifty200.symbols) == 200
    assert set(nifty50.symbols) < set(nifty100.symbols) < set(nifty200.symbols) < set(nifty500.symbols)
    assert isinstance(Nifty50Universe().get_snapshot().symbols, tuple)


def test_scan_dep_composes_from_strategy_evaluation_not_upstox_or_demo():
    """Wiring check: universe scan report depends on strategy evaluation, not Upstox/Demo."""
    from app.api import deps

    params = inspect.signature(deps.get_universe_scan_report_service).parameters
    evaluation_param = params["evaluation_service"]
    assert evaluation_param.default.dependency is get_strategy_evaluation_service

    strategy_params = inspect.signature(get_strategy_evaluation_service).parameters
    assert "query_service" in strategy_params

    assert "provider" not in params
    assert "upstox" not in params
    upstox_sig = inspect.signature(get_upstox_provider)
    assert upstox_sig.parameters
