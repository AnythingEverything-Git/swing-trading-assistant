"""Typed configuration using `pydantic-settings` BaseSettings.

This file exposes a Settings class to be used by application and infra. The
`BaseSettings` implementation was moved out of Pydantic into the
`pydantic-settings` package; import from there and use `model_config` to set
the env file.

Upstox market-data configuration (no OAuth flow in-app):
  UPSTOX_API_BASE_URL   — optional; defaults to https://api.upstox.com in the provider
  UPSTOX_ACCESS_TOKEN   — Bearer token for historical candle requests

Do not use UPSTOX_API_KEY / UPSTOX_API_SECRET for this provider; they are not read.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    environment: str = "development"
    # Optional Upstox configuration (no secrets committed)
    upstox_api_base_url: str | None = None
    upstox_access_token: str | None = None

    model_config = {"env_file": ".env"}


def get_settings() -> Settings:
    return Settings()
