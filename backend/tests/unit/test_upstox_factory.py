import asyncio
from types import SimpleNamespace
import pytest

from app.infrastructure.market_data.factory import UpstoxProviderFactory


class FakeAsyncClient:
    def __init__(self, timeout=None):
        self.timeout = timeout
        self.closed = False

    async def aclose(self):
        self.closed = True


def test_factory_reads_settings_and_wires_provider(monkeypatch):
    fake_settings = SimpleNamespace(upstox_api_base_url="https://api.fake", upstox_access_token="tok")
    monkeypatch.setattr("app.infrastructure.market_data.factory.get_settings", lambda: fake_settings)

    factory = UpstoxProviderFactory(client_cls=FakeAsyncClient)

    async def _run():
        provider = await factory.startup()
        assert provider is not None
        # provider should have been configured with the settings values
        assert provider._base_url == "https://api.fake"
        assert provider._token == "tok"

        # shutdown closes the fake client
        await factory.shutdown()
        assert factory._client is None

    asyncio.run(_run())


def test_factory_respects_explicit_args_and_instrument_mapping():
    fake_map = {"SYM": "UPSTOX:SYM"}
    factory = UpstoxProviderFactory(client_cls=FakeAsyncClient, instrument_key_map=fake_map)

    async def _run():
        provider = await factory.startup(base_url="https://custom", access_token="x")
        assert provider._base_url == "https://custom"
        assert provider._token == "x"
        assert provider._instrument_key_map is fake_map
        await factory.shutdown()

    asyncio.run(_run())


def test_factory_client_lifecycle_callable_integration():
    # Ensure that a passed client class is used and closed via aclose
    factory = UpstoxProviderFactory(client_cls=FakeAsyncClient)

    async def _run():
        _ = await factory.startup(base_url="https://x", access_token="t")
        # client instance should be FakeAsyncClient
        assert isinstance(factory._client, FakeAsyncClient)
        await factory.shutdown()
        assert factory._client is None

    asyncio.run(_run())
