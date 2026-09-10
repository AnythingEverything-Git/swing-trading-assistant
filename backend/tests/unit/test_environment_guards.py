"""Environment mix guards for local-dev vs AWS-release."""
from __future__ import annotations

import pytest

from app.core.config import Settings, validate_runtime_settings


def test_production_rejects_demo() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:x@postgres:5432/swingdb",
        environment="production",
        market_data_source="demo",
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="forbids MARKET_DATA_SOURCE=demo"):
        validate_runtime_settings(settings)


def test_production_allows_upstox() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:x@postgres:5432/swingdb",
        environment="production",
        market_data_source="upstox",
        upstox_access_token="token",
        _env_file=None,
    )
    validate_runtime_settings(settings)


def test_development_rejects_remote_db_host() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:x@13.235.110.243:5432/swingdb",
        environment="development",
        market_data_source="demo",
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="refuses DATABASE_URL host"):
        validate_runtime_settings(settings)


def test_development_allows_localhost() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/swingdb",
        environment="development",
        market_data_source="demo",
        _env_file=None,
    )
    validate_runtime_settings(settings)
