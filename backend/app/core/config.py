"""Typed configuration using Pydantic BaseSettings (v2).

This file exposes a Settings class to be used by application and infra.
"""
from pydantic import BaseSettings


class Settings(BaseSettings):
    database_url: str
    environment: str = "development"

    class Config:
        env_file = ".env"


def get_settings() -> Settings:
    return Settings()
