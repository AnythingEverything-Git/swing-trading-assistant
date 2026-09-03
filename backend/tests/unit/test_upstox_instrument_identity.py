"""Focused tests for Upstox config and NSE symbol -> instrument_key mapping."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.config import Settings
from app.infrastructure.market_data.instrument_key_map import (
    FileBackedInstrumentKeyMap,
    load_default_nse_instrument_key_map,
)
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider
from app.infrastructure.market_data.upstox_provider import UpstoxAPIError, UpstoxMarketDataProvider
from app.domain.market_data.provider import MarketDataProvider


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    async def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse):
        self._resp = response
        self.last_request = None

    async def get(self, url, params=None, headers=None, timeout=None):
        self.last_request = dict(url=url, params=params, headers=headers, timeout=timeout)
        return self._resp


def test_settings_reads_upstox_access_token_and_base_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "demo-token")
    monkeypatch.setenv("UPSTOX_API_BASE_URL", "https://api.example.test")
    # Ensure legacy names are not required
    monkeypatch.delenv("UPSTOX_API_KEY", raising=False)
    monkeypatch.delenv("UPSTOX_API_SECRET", raising=False)

    settings = Settings()

    assert settings.upstox_access_token == "demo-token"
    assert settings.upstox_api_base_url == "https://api.example.test"


def test_known_nse_symbol_resolves_to_configured_instrument_key():
    resolver = load_default_nse_instrument_key_map()

    assert resolver.resolve("RELIANCE") == "NSE_EQ|INE002A01018"
    assert resolver.resolve("tcs") == "NSE_EQ|INE467B01029"
    assert resolver.resolve(" INFY ") == "NSE_EQ|INE009A01021"
    assert resolver.resolve("HDFCBANK") == "NSE_EQ|INE040A01034"


def test_unknown_symbol_fails_clearly(tmp_path: Path):
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps({"version": "t", "mappings": {"RELIANCE": "NSE_EQ|INE002A01018"}}),
        encoding="utf-8",
    )
    resolver = FileBackedInstrumentKeyMap(path)

    with pytest.raises(UpstoxAPIError, match="Instrument mapping missing for symbol: UNKNOWN"):
        resolver.resolve("UNKNOWN")


@pytest.mark.asyncio
async def test_provider_uses_resolved_instrument_key_in_request_url():
    payload = {"status": "success", "data": {"candles": []}}
    client = FakeClient(FakeResponse(200, payload))
    resolver = load_default_nse_instrument_key_map()
    provider = UpstoxMarketDataProvider(
        client,
        base_url="https://api.test",
        access_token="tok",
        instrument_key_map=resolver,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 10, tzinfo=timezone.utc)
    await provider.get_candles("RELIANCE", "1d", start, end)

    assert client.last_request is not None
    assert client.last_request["headers"]["Authorization"] == "Bearer tok"
    assert (
        client.last_request["url"]
        == "https://api.test/v3/historical-candle/NSE_EQ%7CINE002A01018/days/1/2024-01-10/2024-01-01"
    )


@pytest.mark.asyncio
async def test_provider_unmapped_symbol_raises_without_http_call():
    client = FakeClient(FakeResponse(200, {"status": "success", "data": {"candles": []}}))
    provider = UpstoxMarketDataProvider(
        client,
        base_url="https://api.test",
        instrument_key_map=load_default_nse_instrument_key_map(),
    )

    with pytest.raises(UpstoxAPIError, match="Instrument mapping missing for symbol: NOTAMAPPED"):
        await provider.get_candles(
            "NOTAMAPPED",
            "1d",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
    assert client.last_request is None


@pytest.mark.asyncio
async def test_mock_market_data_provider_behavior_unchanged():
    provider = MockMarketDataProvider()
    assert isinstance(provider, MarketDataProvider)
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 1, 2, tzinfo=timezone.utc)
    candles = await provider.get_candles("ANY", "1d", start, end)
    assert len(candles) == 2
    assert all(c.symbol == "ANY" for c in candles)
