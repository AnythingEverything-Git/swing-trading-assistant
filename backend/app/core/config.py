"""Typed configuration using `pydantic-settings` BaseSettings.

This file exposes a Settings class to be used by application and infra. The
`BaseSettings` implementation was moved out of Pydantic into the
`pydantic-settings` package; import from there and use `model_config` to set
the env file.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    environment: str = "development"

    model_config = {"env_file": ".env"}


def get_settings() -> Settings:
    return Settings()
