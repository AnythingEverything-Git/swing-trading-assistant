"""Factory / wiring for Upstox market-data provider.

Creates an `httpx.AsyncClient` and wires it into `UpstoxMarketDataProvider`.
The factory keeps HTTP client lifecycle explicit so callers can start and
stop the client during application startup/shutdown.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping
from types import SimpleNamespace

from app.core.config import get_settings
from .upstox_provider import UpstoxMarketDataProvider


class UpstoxProviderFactory:
    """Create and manage an UpstoxMarketDataProvider and its HTTP client.

    Usage:
      factory = UpstoxProviderFactory(instrument_key_map=..., client_cls=httpx.AsyncClient)
      await factory.startup()  # creates client and provider
      provider = factory.provider
      await factory.shutdown()  # closes httpx client
    """

    def __init__(
        self,
        instrument_key_map: Mapping[str, str] | Callable[[str], str] | None = None,
        client_cls: Callable[..., Any] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._instrument_key_map = instrument_key_map
        self._client_cls = client_cls
        self._timeout = timeout

        self._client = None
        self._provider: UpstoxMarketDataProvider | None = None

    @property
    def provider(self) -> UpstoxMarketDataProvider | None:
        return self._provider

    async def startup(self, base_url: str | None = None, access_token: str | None = None) -> UpstoxMarketDataProvider:
        """Create HTTP client and UpstoxMarketDataProvider.

        If `base_url` or `access_token` are omitted the factory will read
        them from application settings via `get_settings()`.
        """
        # lazy import to avoid optional httpx requirement at module import
        if self._client is not None:
            return self._provider

        # Only load settings if base_url or access_token are not provided
        settings = None
        if base_url is None or access_token is None:
            settings = get_settings()

        # Resolve base_url and token from args or settings
        resolved_base = base_url or (getattr(settings, "upstox_api_base_url", None) if settings else None)
        resolved_token = access_token or (getattr(settings, "upstox_access_token", None) if settings else None)

        # Create HTTP client using injected client class or httpx.AsyncClient
        if self._client_cls is None:
            try:
                import httpx

                client_cls = httpx.AsyncClient
            except Exception as exc:  # pragma: no cover - httpx must be present in dev env
                raise RuntimeError("httpx is required to create real HTTP clients") from exc
        else:
            client_cls = self._client_cls

        # instantiate client with reasonable defaults
        self._client = client_cls(timeout=self._timeout)

        # Create provider wired to the client
        self._provider = UpstoxMarketDataProvider(
            self._client,
            base_url=resolved_base,
            access_token=resolved_token,
            instrument_key_map=self._instrument_key_map,
            timeout=self._timeout,
        )
        return self._provider

    async def shutdown(self) -> None:
        """Close the HTTP client if created."""
        if self._client is None:
            return

        aclose = getattr(self._client, "aclose", None)
        if aclose is None:
            # nothing to do
            self._client = None
            self._provider = None
            return

        await aclose()
        self._client = None
        self._provider = None


__all__ = ["UpstoxProviderFactory"]
