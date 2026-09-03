"""Focused tests for repository-root Settings / .env resolution."""
from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, default_env_file, get_settings, repository_root


def test_default_env_file_is_absolute_repo_root_dotenv():
    env_path = default_env_file()
    root = repository_root()

    assert env_path.is_absolute()
    assert env_path == root / ".env"
    assert (root / "backend" / "app" / "core" / "config.py").is_file()
    assert env_path.name == ".env"


def test_settings_loads_root_env_when_cwd_is_not_repo_root(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("UPSTOX_API_BASE_URL", raising=False)
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)

    elsewhere = tmp_path / "not-the-repo"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    # Must not depend on CWD-relative ".env"; absolute path from config.py location.
    assert not (Path.cwd() / ".env").exists()
    assert default_env_file().is_file()

    settings = Settings()
    assert isinstance(settings.database_url, str)
    assert settings.database_url.strip() != ""
    # Do not print or assert the concrete secret/URL value beyond non-emptiness.


def test_explicit_environment_variables_override_dotenv(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ENVIRONMENT", "test-override")
    monkeypatch.setenv("UPSTOX_API_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "demo-token")

    settings = get_settings()

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.environment == "test-override"
    assert settings.upstox_api_base_url == "https://api.example.test"
    assert settings.upstox_access_token == "demo-token"
