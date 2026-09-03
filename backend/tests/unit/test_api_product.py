from fastapi.testclient import TestClient

from app.api.deps import get_product_status_service
from app.api.main import create_app
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
        )


def test_product_status_reports_demo_and_plug_and_play():
    app = create_app()
    app.dependency_overrides[get_product_status_service] = lambda: FakeProductStatusService()
    client = TestClient(app)
    resp = client.get("/api/v1/product/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_source"] == "demo"
    assert data["live_ready"] is False
    assert "not live" in data["claim"].lower()
    assert data["symbols_with_candles"] == 12
    assert "UPSTOX_ACCESS_TOKEN" in data["plug_and_play"]
