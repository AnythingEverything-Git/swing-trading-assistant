"""Upstox market-data adapter (Historical Candle V3).

Implements the `MarketDataProvider` protocol and calls the Upstox
V3 historical-candle endpoint. The adapter keeps Upstox-specific logic
inside infrastructure and returns domain `Candle` objects.

Design notes:
- Accepts an injected async HTTP client with an async `get()` method.
- Requires an Upstox `instrument_key` to build the V3 path. To avoid
    coupling the domain to Upstox, the provider accepts an optional
    `instrument_key_map` (dict or callable) to translate domain `symbol`
    into an Upstox `instrument_key`. If no mapping is provided the
    `symbol` argument is treated as the instrument_key (caller must
    supply a real Upstox instrument_key in that case).
"""
from __future__ import annotations

from typing import Any, List, Callable, Mapping
from datetime import datetime, timezone, date
from decimal import Decimal
from urllib.parse import quote

from app.domain.market_data import Candle
from app.domain.market_data.provider import MarketDataProvider
from app.core.config import get_settings

class UpstoxAPIError(RuntimeError):
    pass


class UpstoxMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        http_client: Any,
        base_url: str | None = None,
        access_token: str | None = None,
        instrument_key_map: Mapping[str, str] | Callable[[str], str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Create provider.

        - `http_client` must implement `async def get(url, params=None, headers=None, timeout=None)`.
        - `base_url` and `access_token` may be provided or picked from settings.
        """
        self._client = http_client
        settings = None
        # Load settings only when neither base_url nor access_token are provided
        if base_url is None and access_token is None:
            settings = get_settings()

        # default base URL when not provided in settings or constructor
        default_base = "https://api.upstox.com"

        self._base_url = base_url or (settings.upstox_api_base_url if settings else None) or default_base
        self._token = access_token or (settings.upstox_access_token if settings else None)
        self._timeout = timeout
        self._instrument_key_map = instrument_key_map

    async def get_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[Candle]:
        # timeframe -> (unit, interval)
        timeframe_map = {
            "1d": ("days", "1"),
            "1w": ("weeks", "1"),
            "1mo": ("months", "1"),
        }

        if timeframe not in timeframe_map:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        if start is None or end is None:
            raise ValueError("start and end required")
        if start > end:
            raise ValueError("start must be <= end")

        if not self._base_url:
            raise UpstoxAPIError("Upstox base URL not configured")

        # Resolve instrument_key: either use mapping callable/dict or treat symbol
        # as an instrument_key directly (caller responsibility).
        instrument_key: str
        if self._instrument_key_map is None:
            instrument_key = symbol
        elif callable(self._instrument_key_map):
            instrument_key = self._instrument_key_map(symbol)
        else:
            # mapping is a Mapping[str,str]
            try:
                instrument_key = self._instrument_key_map[symbol]
            except KeyError as exc:
                raise UpstoxAPIError(f"Instrument mapping missing for symbol: {symbol}") from exc

        if not instrument_key:
            raise UpstoxAPIError("instrument_key is required for Upstox provider")

        unit, interval = timeframe_map[timeframe]

        # Convert dates to YYYY-MM-DD (API expects date strings)
        from_date = start.date().isoformat()
        to_date = end.date().isoformat()

        # Build V3 path: /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
        # Encode instrument_key so keys containing '|' (e.g. NSE_EQ|INE...) are valid URL path segments.
        encoded_key = quote(str(instrument_key), safe="")
        url = f"{self._base_url.rstrip('/')}/v3/historical-candle/{encoded_key}/{unit}/{interval}/{to_date}/{from_date}"

        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = await self._client.get(url, headers=headers, timeout=self._timeout)

        status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status is None or int(status) >= 400:
            raise UpstoxAPIError(f"Upstox API error: status={status}")

        try:
            payload = await resp.json()
        except Exception as exc:
            raise UpstoxAPIError("Invalid JSON from Upstox") from exc

        # Validate V3 response structure
        if not isinstance(payload, dict):
            raise UpstoxAPIError("Malformed Upstox response: expected JSON object")

        if payload.get("status") != "success":
            raise UpstoxAPIError("Upstox reported non-success status")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise UpstoxAPIError("Malformed Upstox response: missing 'data' object")

        candles_arr = data.get("candles")
        if candles_arr is None:
            raise UpstoxAPIError("Malformed Upstox response: missing 'candles'")
        if not isinstance(candles_arr, list):
            raise UpstoxAPIError("Malformed Upstox response: 'candles' must be a list")

        result: List[Candle] = []
        for idx, rec in enumerate(candles_arr):
            if not isinstance(rec, (list, tuple)):
                raise UpstoxAPIError("Malformed candle entry: must be an array")
            if len(rec) < 6:
                raise UpstoxAPIError("Malformed candle entry: expected at least 6 fields")

            # [timestamp, open, high, low, close, volume, open_interest]
            ts_raw = rec[0]
            try:
                if isinstance(ts_raw, (int, float)):
                    # epoch seconds vs milliseconds heuristic
                    ts_val = float(ts_raw)
                    if ts_val > 1e12:
                        # milliseconds
                        ts = datetime.fromtimestamp(ts_val / 1000.0, tz=timezone.utc)
                    else:
                        ts = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                elif isinstance(ts_raw, str):
                    ts = datetime.fromisoformat(ts_raw)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                else:
                    raise ValueError("unsupported timestamp type")
            except Exception as exc:
                raise UpstoxAPIError(f"Invalid timestamp in candle at index {idx}") from exc

            try:
                open_p = Decimal(str(rec[1]))
                high_p = Decimal(str(rec[2]))
                low_p = Decimal(str(rec[3]))
                close_p = Decimal(str(rec[4]))
                vol_val = rec[5]
                vol_int = int(vol_val) if vol_val is not None else None
            except Exception as exc:
                raise UpstoxAPIError(f"Invalid numeric fields in candle at index {idx}") from exc

            result.append(
                Candle(
                    symbol=symbol,
                    exchange="UPSTOX",
                    instrument_id=instrument_key,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=vol_int,
                )
            )

        # Chronological order
        result.sort(key=lambda c: c.timestamp)
        return result
