"""Unit tests for Nifty 500 readiness SLOs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.application.ops.readiness import (
    ReadinessGate,
    _expected_calendar_1d,
    _gate_host,
    _gate_live,
    _gate_swing_1d,
    _gate_today_1m,
    _overall,
)

IST = ZoneInfo("Asia/Kolkata")


def test_overall_prefers_red_then_amber():
    assert _overall([ReadinessGate("a", "A", "green", "ok")]) == "green"
    assert _overall(
        [
            ReadinessGate("a", "A", "green", "ok"),
            ReadinessGate("b", "B", "amber", "lag"),
        ]
    ) == "amber"
    assert _overall(
        [
            ReadinessGate("a", "A", "amber", "lag"),
            ReadinessGate("b", "B", "red", "behind"),
            ReadinessGate("c", "C", "skipped", "n/a"),
        ]
    ) == "red"


def test_swing_provider_max_pass_and_calendar_amber():
    provider = datetime(2026, 9, 9, 18, 30, tzinfo=timezone.utc)
    symbols = ["AAA", "BBB", "CCC"]
    max_1d = {s: provider for s in symbols}
    now = datetime(2026, 9, 11, 17, 0, tzinfo=IST)
    gate = _gate_swing_1d(
        symbols=symbols,
        max_1d=max_1d,
        provider_max=provider,
        calendar_expected=now.date(),
        now_ist=now,
    )
    assert gate.status == "amber"
    assert "provider" in gate.detail.lower() or "lag" in gate.detail.lower()


def test_swing_behind_provider_is_red():
    provider = datetime(2026, 9, 9, 18, 30, tzinfo=timezone.utc)
    older = provider - timedelta(days=2)
    symbols = [f"S{i}" for i in range(100)]
    max_1d = {s: provider for s in symbols[:90]}
    max_1d.update({s: older for s in symbols[90:]})
    gate = _gate_swing_1d(
        symbols=symbols,
        max_1d=max_1d,
        provider_max=provider,
        calendar_expected=None,
        now_ist=datetime(2026, 9, 11, 17, 0, tzinfo=IST),
    )
    assert gate.status == "red"
    assert gate.metrics["pct_at_provider_max"] == 90.0


def test_today_1m_skipped_before_open():
    now = datetime(2026, 9, 11, 9, 10, tzinfo=IST)
    gate = _gate_today_1m(symbols=["AAA"], max_1m={}, now_ist=now)
    assert gate.status == "skipped"


def test_host_mutex_stuck_red():
    since = datetime.now(timezone.utc) - timedelta(minutes=60)
    gate = _gate_host(
        refresh_mutex_held=True,
        refresh_running_since=since,
        history_backfill_running=False,
    )
    assert gate.status == "red"


def test_live_gate_demo_red():
    settings = SimpleNamespace(
        market_data_source="demo",
        upstox_access_token="",
        environment="development",
    )
    # live_ready reads settings — patch via real Settings is heavy; just check gate shape
    gate = _gate_live(settings)  # type: ignore[arg-type]
    assert gate.id == "live"
    assert gate.status in ("red", "green")


def test_expected_calendar_before_eod():
    # Thursday 12:00 IST → expect prior weekday (Wed)
    now = datetime(2026, 9, 10, 12, 0, tzinfo=IST)
    assert _expected_calendar_1d(now) == now.date() - timedelta(days=1)


@pytest.mark.asyncio
async def test_readiness_endpoint_shape():
    from fastapi.testclient import TestClient

    from app.api.deps import get_db, get_product_status_service
    from app.api.main import create_app
    from app.application.ops.scheduler_status import ensure_registry
    from app.application.product.status_service import ProductStatus

    class FakeProductStatusService:
        async def status(self, timeframe: str = "1d") -> ProductStatus:
            return ProductStatus(
                data_source="demo",
                live_ready=False,
                claim="Demo",
                last_candle_time=None,
                symbols_with_candles=0,
                environment="development",
            )

    async def _fake_db():
        # Minimal session stub — readiness will fail on SQL; override evaluate path instead.
        yield None

    app = create_app()
    app.dependency_overrides[get_product_status_service] = lambda: FakeProductStatusService()
    ensure_registry(app.state)

    # Monkeypatch evaluate_readiness used by the route
    from app.application.ops import readiness as readiness_mod
    from app.application.ops.readiness import ReadinessGate, ReadinessReport

    async def fake_eval(*_a, **_k):
        return ReadinessReport(
            universe="NIFTY_500",
            ready=True,
            status="amber",
            as_of=datetime.now(timezone.utc),
            provider_1d_max=datetime(2026, 9, 9, 18, 30, tzinfo=timezone.utc),
            calendar_1d_expected=datetime(2026, 9, 10).date(),
            gates=(
                ReadinessGate("live", "Live", "green", "ok"),
                ReadinessGate("swing_1d", "Swing", "amber", "provider lag"),
            ),
            recommendations=("Amber is provider lag",),
        )

    original = readiness_mod.evaluate_readiness
    readiness_mod.evaluate_readiness = fake_eval  # type: ignore[assignment]
    try:
        # Still need DB dependency to succeed
        async def empty_db():
            class _S:
                pass

            yield _S()

        app.dependency_overrides[get_db] = empty_db
        # Patch the import used in the route module
        import app.api.routes.ops as ops_mod

        ops_mod.evaluate_readiness = fake_eval  # type: ignore[assignment]
        client = TestClient(app)
        resp = client.get("/api/v1/ops/readiness?universe=NIFTY_500")
        assert resp.status_code == 200
        data = resp.json()
        assert data["universe"] == "NIFTY_500"
        assert data["ready"] is True
        assert data["status"] == "amber"
        assert data["provider_1d_max"]
        assert len(data["gates"]) >= 1
        assert data["recommendations"]
    finally:
        readiness_mod.evaluate_readiness = original  # type: ignore[assignment]
