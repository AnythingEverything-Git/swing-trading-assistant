from fastapi.testclient import TestClient

from app.api.deps import get_product_status_service
from app.api.main import create_app
from app.application.ops.scheduler_status import ensure_registry
from app.application.product.status_service import ProductStatus


class FakeProductStatusService:
    async def status(self, timeframe: str = "1d") -> ProductStatus:
        return ProductStatus(
            data_source="demo",
            live_ready=False,
            claim="Demo candles — not live market data",
            last_candle_time=None,
            symbols_with_candles=12,
            environment="development",
            symbols_with_1m=8,
            last_1m_candle_time=None,
            stale_risk="High",
        )


def test_ops_schedulers_get_and_heartbeat():
    app = create_app()
    app.dependency_overrides[get_product_status_service] = lambda: FakeProductStatusService()
    client = TestClient(app)
    ensure_registry(app.state)

    resp = client.get("/api/v1/ops/schedulers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_source"] in ("demo", "upstox")
    assert data["stale_risk"] == "High"
    assert data["symbols_with_candles"] == 12
    job_ids = [j["job_id"] for j in data["jobs"]]
    assert job_ids == [
        "inapp_1d",
        "inapp_1m",
        "cron_1m_today",
        "cron_1d",
        "cron_1d_paced",
        "cron_readiness",
        "cron_watchdog",
        "cron_universe",
        "host_catchup",
        "host_1m_history",
    ]

    hb = client.post(
        "/api/v1/ops/schedulers/heartbeat",
        json={"job_id": "cron_1m_today", "status": "running", "detail": "start"},
    )
    assert hb.status_code == 200
    assert hb.json()["job"]["running"] is True
    assert hb.json()["job"]["last_status"] == "running"

    done = client.post(
        "/api/v1/ops/schedulers/heartbeat",
        json={"job_id": "cron_1m_today", "status": "ok", "detail": "done"},
    )
    assert done.status_code == 200
    assert done.json()["job"]["running"] is False
    assert done.json()["job"]["last_status"] == "ok"

    bad = client.post(
        "/api/v1/ops/schedulers/heartbeat",
        json={"job_id": "not_a_job", "status": "ok"},
    )
    assert bad.status_code == 400


def test_ops_enable_and_run_endpoints():
    app = create_app()
    app.dependency_overrides[get_product_status_service] = lambda: FakeProductStatusService()
    client = TestClient(app)
    ensure_registry(app.state)

    disabled = client.patch("/api/v1/ops/schedulers/inapp_1d", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    blocked = client.post("/api/v1/ops/schedulers/inapp_1d/run")
    assert blocked.status_code == 409

    enabled = client.patch("/api/v1/ops/schedulers/inapp_1d", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    unsupported = client.post("/api/v1/ops/schedulers/host_catchup/run")
    assert unsupported.status_code == 400

    one = client.get("/api/v1/ops/schedulers/cron_1d")
    assert one.status_code == 200
    assert one.json()["job_id"] == "cron_1d"
    assert one.json()["can_run"] is True
