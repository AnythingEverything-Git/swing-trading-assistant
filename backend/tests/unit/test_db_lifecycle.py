import os
import asyncio

from fastapi.testclient import TestClient

import pytest
from app.api.main import create_app
from app.infrastructure import database as db_module
from app.infrastructure.database.base import Base


def test_startup_creates_engine_and_sessionmaker():
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    app = create_app()
    with TestClient(app):
        assert hasattr(app.state, "engine")
        assert hasattr(app.state, "sessionmaker")


def test_request_obtains_db_session():
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    app = create_app()
    with TestClient(app) as client:
        # create tables so queries succeed
        engine = app.state.engine

        async def _create():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(_create())

        # basic request should succeed (unknown symbol -> empty list)
        resp = client.get("/api/v1/market-data/candles/FOO?start=2020-01-01T00:00:00Z&end=2020-01-02T00:00:00Z&timeframe=1d")
        assert resp.status_code == 200


def test_shutdown_disposes_engine(monkeypatch):
    # Monkeypatch create_engine to wrap engine.dispose and record flag
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    original_create_engine = db_module.session.create_engine

    def wrapper(db_url, echo: bool = False):
        real_engine = original_create_engine(db_url, echo=echo)

        class EngineProxy:
            def __init__(self, engine):
                self._engine = engine
                self._was_disposed = False

            def __getattr__(self, name):
                return getattr(self._engine, name)

            async def dispose(self):
                self._was_disposed = True
                await self._engine.dispose()

        return EngineProxy(real_engine)

    monkeypatch.setattr(db_module.session, "create_engine", wrapper)

    app = create_app()
    with TestClient(app):
        assert hasattr(app.state, "engine")

    # after exiting TestClient, shutdown should have run and disposed the engine
    engine = getattr(app.state, "engine", None)
    assert engine is not None
    assert getattr(engine, "_was_disposed", False) is True


def test_missing_db_fails_clearly(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # Root `.env` is resolved by absolute path from config.py; isolate this test
    # so "missing DATABASE_URL" is not satisfied by the repository-root file.
    from app.core.config import Settings

    def _settings_without_repo_dotenv():
        return Settings(_env_file=tmp_path / "missing.env")

    monkeypatch.setattr("app.api.main.get_settings", _settings_without_repo_dotenv)

    app = create_app()
    # entering the TestClient should fail during startup due to missing DB settings
    with pytest.raises(Exception):
        with TestClient(app):
            pass
