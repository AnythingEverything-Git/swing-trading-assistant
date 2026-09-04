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

from typing import Any, List, Callable, Mapping, Iterable
from datetime import datetime, timezone, date
from decimal import Decimal
from inspect import isawaitable
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

    def _resolve_instrument_key(self, symbol: str) -> str:
        instrument_key: str
        if self._instrument_key_map is None:
            instrument_key = symbol
        elif callable(self._instrument_key_map):
            instrument_key = self._instrument_key_map(symbol)
        else:
            try:
                instrument_key = self._instrument_key_map[symbol]
            except KeyError as exc:
                raise UpstoxAPIError(f"Instrument mapping missing for symbol: {symbol}") from exc
        if not instrument_key:
            raise UpstoxAPIError("instrument_key is required for Upstox provider")
        return instrument_key

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

        instrument_key = self._resolve_instrument_key(symbol)

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
            payload = resp.json()
            if isawaitable(payload):
                payload = await payload
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

    async def get_last_traded_prices(self, symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
        if not self._base_url:
            raise UpstoxAPIError("Upstox base URL not configured")
        symbols_list = [symbol.strip() for symbol in symbols if symbol and symbol.strip()]
        if not symbols_list:
            return {}

        instrument_keys: list[str] = []
        for symbol in symbols_list:
            key = self._resolve_instrument_key(symbol)
            instrument_keys.append(key)

        encoded_keys = ",".join(instrument_keys)
        url = f"{self._base_url.rstrip('/')}/v2/market-quote/quotes"
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = await self._client.get(
            url,
            params={"instrument_key": encoded_keys},
            headers=headers,
            timeout=self._timeout,
        )
        status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status is None or int(status) >= 400:
            raise UpstoxAPIError(f"Upstox quote API error: status={status}")

        try:
            payload = resp.json()
            if isawaitable(payload):
                payload = await payload
        except Exception as exc:
            raise UpstoxAPIError("Invalid JSON from Upstox quote API") from exc

        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise UpstoxAPIError("Malformed Upstox quote response")

        raw_data = payload.get("data")
        if not isinstance(raw_data, dict):
            return {}

        result: dict[str, dict[str, Any]] = {}
        for instrument_key, item in raw_data.items():
            if not isinstance(item, dict):
                continue
            # Upstox typically returns data keys like "NSE_EQ:TCS" but also includes the trading
            # symbol inside each item (field name: "symbol"). Use that for robust mapping.
            symbol = item.get("symbol") or None
            if not symbol:
                # Fallback: parse key after ":" if present
                if isinstance(instrument_key, str) and ":" in instrument_key:
                    symbol = instrument_key.split(":", 1)[1]
                else:
                    continue
            symbol = str(symbol).strip().upper()
            ltp = item.get("last_price")
            if ltp is None:
                continue
            try:
                ltp_decimal = Decimal(str(ltp))
            except Exception:
                continue
            result[symbol] = {
                "last_price": ltp_decimal,
                "instrument_key": instrument_key,
                "raw": item,
            }
        return result

    async def get_option_chain(self, symbol: str, expiry_date: str = "current_month") -> dict[str, Any]:
        """Fetch put/call option chain for an underlying NSE equity symbol."""
        if not self._base_url:
            raise UpstoxAPIError("Upstox base URL not configured")
        if not self._token:
            raise UpstoxAPIError("Upstox access token required for option chain")

        instrument_key = self._resolve_instrument_key(symbol)
        url = f"{self._base_url.rstrip('/')}/v2/option/chain"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        resp = await self._client.get(
            url,
            params={"instrument_key": instrument_key, "expiry_date": expiry_date},
            headers=headers,
            timeout=self._timeout,
        )
        status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status is None or int(status) >= 400:
            raise UpstoxAPIError(f"Upstox option chain API error: status={status}")

        try:
            payload = resp.json()
            if isawaitable(payload):
                payload = await payload
        except Exception as exc:
            raise UpstoxAPIError("Invalid JSON from Upstox option chain API") from exc

        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise UpstoxAPIError("Malformed Upstox option chain response")

        data = payload.get("data")
        if not isinstance(data, list):
            return {
                "symbol": symbol.upper(),
                "instrument_key": instrument_key,
                "expiry_date": expiry_date,
                "rows": [],
                "pcr": None,
                "spot": None,
            }

        rows: list[dict[str, Any]] = []
        spot: Decimal | None = None
        pcr: Decimal | None = None
        for item in data:
            if not isinstance(item, dict):
                continue
            if spot is None and item.get("underlying_spot_price") is not None:
                try:
                    spot = Decimal(str(item["underlying_spot_price"]))
                except Exception:
                    spot = None
            if pcr is None and item.get("pcr") is not None:
                try:
                    pcr = Decimal(str(item["pcr"]))
                except Exception:
                    pcr = None

            call = item.get("call_options") if isinstance(item.get("call_options"), dict) else {}
            put = item.get("put_options") if isinstance(item.get("put_options"), dict) else {}
            call_md = call.get("market_data") if isinstance(call.get("market_data"), dict) else {}
            put_md = put.get("market_data") if isinstance(put.get("market_data"), dict) else {}
            call_g = call.get("option_greeks") if isinstance(call.get("option_greeks"), dict) else {}
            put_g = put.get("option_greeks") if isinstance(put.get("option_greeks"), dict) else {}

            def _num(payload: dict[str, Any], key: str) -> Decimal | None:
                raw = payload.get(key)
                if raw is None:
                    return None
                try:
                    return Decimal(str(raw))
                except Exception:
                    return None

            rows.append(
                {
                    "strike": _num(item, "strike_price"),
                    "expiry": item.get("expiry"),
                    "call_ltp": _num(call_md, "ltp"),
                    "call_oi": _num(call_md, "oi"),
                    "call_iv": _num(call_g, "iv"),
                    "put_ltp": _num(put_md, "ltp"),
                    "put_oi": _num(put_md, "oi"),
                    "put_iv": _num(put_g, "iv"),
                }
            )

        rows = [row for row in rows if row.get("strike") is not None]
        rows.sort(key=lambda row: row["strike"])
        return {
            "symbol": symbol.upper(),
            "instrument_key": instrument_key,
            "expiry_date": expiry_date,
            "expiry": rows[0]["expiry"] if rows else None,
            "spot": spot,
            "pcr": pcr,
            "rows": rows,
        }
