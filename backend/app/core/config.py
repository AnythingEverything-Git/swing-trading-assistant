"""Typed configuration using `pydantic-settings` BaseSettings.

This file exposes a Settings class to be used by application and infra. The
`BaseSettings` implementation was moved out of Pydantic into the
`pydantic-settings` package; import from there and use `model_config` to set
the env file.

Upstox market-data configuration (no OAuth flow in-app):
  MARKET_DATA_SOURCE    — demo (default) or upstox. Scan always reads PostgreSQL.
  UPSTOX_API_BASE_URL   — optional; defaults to https://api.upstox.com in the provider
  UPSTOX_ACCESS_TOKEN   — Bearer token for historical candle requests

Plug-and-play live: set MARKET_DATA_SOURCE=upstox and UPSTOX_ACCESS_TOKEN, restart,
then `python scripts/refresh_market_data.py`. Do not silently fall back to demo.

Do not use UPSTOX_API_KEY / UPSTOX_API_SECRET for this provider; they are not read.

Email alerts (Amazon SES SMTP by default):
  EMAIL_PROVIDER              — ses (default) or smtp
  AWS_SES_REGION              — e.g. ap-south-1 → host email-smtp.ap-south-1.amazonaws.com
  AWS_SES_SMTP_USERNAME       — SES SMTP username from the SES console
  AWS_SES_SMTP_PASSWORD       — SES SMTP password (create SMTP credentials; not the AWS console password)
  ALERT_FROM_EMAIL            — must be a SES-verified identity
  ALERT_TO_EMAILS             — comma-separated; must be verified while SES is in sandbox

Research insights (optional Gemini Flash):
  NARRATIVE_PROVIDER          — template (default) or llm
  GOOGLE_API_KEY              — Google AI Studio key when NARRATIVE_PROVIDER=llm
  GEMINI_MODEL                — default gemini-2.0-flash

The repository-root `.env` is resolved from this file's location so scripts work
whether launched from the repo root, `backend/`, or another working directory.
Process environment variables still take precedence over the `.env` file.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def repository_root() -> Path:
    """Return the repository root (parent of `backend/`).

    `config.py` lives at `backend/app/core/config.py` → parents[3] is the root.
    """
    return Path(__file__).resolve().parents[3]


def default_env_file() -> Path:
    """Absolute path to the repository-root `.env` (not CWD-relative)."""
    return repository_root() / ".env"


class Settings(BaseSettings):
    database_url: str
    environment: str = "development"
    # Candle ingest source. Scan/evaluate/backtest always read PostgreSQL.
    # demo  — DemoMarketDataProvider (default until live token exists)
    # upstox — Upstox historical API; requires UPSTOX_ACCESS_TOKEN
    market_data_source: str = "demo"
    # Optional Upstox configuration (no secrets committed)
    upstox_api_base_url: str | None = None
    upstox_access_token: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    narrative_provider: str = "template"
    google_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    # Email alerts: "ses" (Amazon SES SMTP) or "smtp" (generic SMTP).
    email_provider: str = "ses"
    aws_ses_region: str = "ap-south-1"
    aws_ses_smtp_username: str | None = None
    aws_ses_smtp_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    alert_from_email: str | None = None
    alert_to_emails: str | None = None  # comma-separated list
    # Pre-market alert schedule (IST 24h format, e.g. "08:45")
    premarket_alert_time: str = "08:45"

    model_config = SettingsConfigDict(
        env_file=default_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
