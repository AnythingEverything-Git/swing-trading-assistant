"""Resolve the ingest market-data provider from Settings.

Scan / evaluate / backtest always read persisted candles. This module only
decides which vendor fills the database. Switching demo → live is:

    MARKET_DATA_SOURCE=upstox
    UPSTOX_ACCESS_TOKEN=<token>
    restart API, then run scripts/refresh_market_data.py
"""
from __future__ import annotations

from typing import Literal

from app.core.config import Settings, get_settings
from app.domain.market_data.provider import MarketDataProvider
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider

MarketDataSourceName = Literal["demo", "upstox"]


def normalize_market_data_source(value: str | None) -> MarketDataSourceName:
    source = (value or "demo").strip().lower()
    if source in {"demo", "upstox"}:
        return source  # type: ignore[return-value]
    raise ValueError("MARKET_DATA_SOURCE must be 'demo' or 'upstox'")


def live_ready(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    token = (settings.upstox_access_token or "").strip()
    return normalize_market_data_source(settings.market_data_source) == "upstox" and bool(token)


def data_claim(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    source = normalize_market_data_source(settings.market_data_source)
    if source == "demo":
        return "Demo candles — not live market data"
    if live_ready(settings):
        return "Live Upstox 1d candles"
    return "Live source selected but UPSTOX_ACCESS_TOKEN is missing"


def resolve_ingest_provider(
    settings: Settings | None = None,
    *,
    upstox_provider: MarketDataProvider | None = None,
) -> MarketDataProvider:
    """Return the provider used to *write* candles. Never silently swap Upstox for demo."""
    settings = settings or get_settings()
    source = normalize_market_data_source(settings.market_data_source)
    if source == "demo":
        return DemoMarketDataProvider()
    if upstox_provider is None:
        raise RuntimeError(
            "MARKET_DATA_SOURCE=upstox requires a started Upstox provider and UPSTOX_ACCESS_TOKEN"
        )
    return upstox_provider


__all__ = [
    "MarketDataSourceName",
    "data_claim",
    "live_ready",
    "normalize_market_data_source",
    "resolve_ingest_provider",
]
