from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.schemas import MarketDataIngestRequest
from app.api.deps import get_ingestion_service
from datetime import datetime, timezone


class FakeSvc:
    def __init__(self, to_return=1, raise_exc=None):
        self.to_return = to_return
        self.raise_exc = raise_exc

    async def ingest(self, symbol, timeframe, start, end):
        if self.raise_exc:
            raise self.raise_exc
        return self.to_return


def test_ingest_success(monkeypatch):
    app = create_app()

    async def _fake_ingestion():
        return FakeSvc(to_return=(2, 1))

    app.dependency_overrides[get_ingestion_service] = _fake_ingestion
    client = TestClient(app)

    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2020-01-01T00:00:00Z",
        "end": "2020-01-02T00:00:00Z",
    }

    resp = client.post("/api/v1/market-data/ingest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TST"
    assert data["candles_fetched"] == 2
    assert data["candles_persisted"] == 1


def test_ingest_invalid_range(monkeypatch):
    app = create_app()

    async def _fake_ingestion():
        return FakeSvc(raise_exc=ValueError("bad range"))

    app.dependency_overrides[get_ingestion_service] = _fake_ingestion
    client = TestClient(app)

    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2020-01-02T00:00:00Z",
        "end": "2020-01-01T00:00:00Z",
    }

    resp = client.post("/api/v1/market-data/ingest", json=payload)
    assert resp.status_code == 400


def test_provider_failure(monkeypatch):
    app = create_app()

    async def _fake_ingestion():
        return FakeSvc(raise_exc=RuntimeError("provider down"))

    app.dependency_overrides[get_ingestion_service] = _fake_ingestion
    client = TestClient(app)

    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2020-01-01T00:00:00Z",
        "end": "2020-01-02T00:00:00Z",
    }

    resp = client.post("/api/v1/market-data/ingest", json=payload)
    assert resp.status_code == 500
