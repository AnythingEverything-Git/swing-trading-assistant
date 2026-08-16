from fastapi.testclient import TestClient

from app.main import app


def test_health_db_success(monkeypatch):
    async def fake_health_check(db_url, timeout_seconds=5.0):
        assert db_url == "postgresql+psycopg://test:test@localhost:5432/testdb"
        return True

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@localhost:5432/testdb",
    )

    monkeypatch.setattr(
        "app.infrastructure.database.session.health_check",
        fake_health_check,
    )

    client = TestClient(app)
    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
    }


def test_health_db_failure(monkeypatch):
    async def fake_health_check(db_url, timeout_seconds=5.0):
        raise RuntimeError("cannot connect")

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@localhost:5432/testdb",
    )

    monkeypatch.setattr(
        "app.infrastructure.database.session.health_check",
        fake_health_check,
    )

    client = TestClient(app)
    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "down",
    }