from app.core.config import Settings
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider
from app.infrastructure.market_data.source import (
    data_claim,
    live_ready,
    normalize_market_data_source,
    resolve_ingest_provider,
)


def test_default_source_is_demo():
    assert normalize_market_data_source(None) == "demo"
    assert normalize_market_data_source("DEMO") == "demo"


def test_demo_claim_never_says_live():
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        market_data_source="demo",
        upstox_access_token="",
    )
    assert live_ready(settings) is False
    assert "not live" in data_claim(settings).lower()
    provider = resolve_ingest_provider(settings, upstox_provider=None)
    assert isinstance(provider, DemoMarketDataProvider)


def test_upstox_without_token_is_not_live_ready():
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        market_data_source="upstox",
        upstox_access_token="  ",
    )
    assert live_ready(settings) is False
    assert "token" in data_claim(settings).lower()
