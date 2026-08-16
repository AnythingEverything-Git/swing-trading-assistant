import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.infrastructure.market_data.upstox_provider import UpstoxMarketDataProvider, UpstoxAPIError
from app.domain.market_data import Candle


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


@pytest.mark.asyncio
async def test_v3_url_and_date_mapping_and_unit_interval():
    # instrument_key must appear in the path, and dates are mapped to YYYY-MM-DD
    payload = {"status": "success", "data": {"candles": []}}
    client = FakeClient(FakeResponse(200, payload))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 1, 10, tzinfo=timezone.utc)
    await prov.get_candles("INSTR_KEY", "1d", start, end)

    assert client.last_request is not None
    assert client.last_request["url"].endswith("/v3/historical-candle/INSTR_KEY/days/1/2020-01-10/2020-01-01")


@pytest.mark.asyncio
async def test_parses_v3_candles_and_sorts_chronologically():
    # Use epoch ms timestamps unordered
    ts1 = 1577923200000  # 2020-01-02T00:00:00Z
    ts0 = 1577836800000  # 2020-01-01T00:00:00Z
    candles = [
        [ts1, "105", "115", "95", "110", 200, 0],
        [ts0, "100", "110", "90", "105", 100, 0],
    ]
    payload = {"status": "success", "data": {"candles": candles}}
    client = FakeClient(FakeResponse(200, payload))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 1, 2, tzinfo=timezone.utc)
    res = await prov.get_candles("KEY", "1d", start, end)

    assert len(res) == 2
    assert res[0].timestamp < res[1].timestamp
    assert res[0].open == Decimal("100")
    assert res[1].volume == 200


@pytest.mark.asyncio
async def test_empty_candles_returns_empty_list():
    payload = {"status": "success", "data": {"candles": []}}
    client = FakeClient(FakeResponse(200, payload))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 1, 1, tzinfo=timezone.utc)
    res = await prov.get_candles("K", "1d", start, end)
    assert res == []


@pytest.mark.asyncio
async def test_unsupported_timeframe_raises():
    client = FakeClient(FakeResponse(200, {"status": "success", "data": {"candles": []}}))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")
    with pytest.raises(ValueError):
        await prov.get_candles("K", "1h", datetime.now(timezone.utc), datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_http_error_raises():
    client = FakeClient(FakeResponse(500, {"status": "error"}))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")
    with pytest.raises(UpstoxAPIError):
        await prov.get_candles("K", "1d", datetime.now(timezone.utc), datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_malformed_response_raises():
    client = FakeClient(FakeResponse(200, {"unexpected": 1}))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")
    with pytest.raises(UpstoxAPIError):
        await prov.get_candles("K", "1d", datetime.now(timezone.utc), datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_candle_entry_too_short_raises():
    payload = {"status": "success", "data": {"candles": [[1234567890, 1, 2]]}}
    client = FakeClient(FakeResponse(200, payload))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")
    with pytest.raises(UpstoxAPIError):
        await prov.get_candles("K", "1d", datetime.now(timezone.utc), datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_instrument_key_mapping_callable_and_timezone_string():
    # mapping callable converts symbol->instrument_key
    def mapper(sym: str) -> str:
        return f"UPSTOX:{sym}"

    ts = "2020-01-01T00:00:00+05:30"
    payload = {"status": "success", "data": {"candles": [[ts, "100", "110", "90", "105", 10, 0]]}}
    client = FakeClient(FakeResponse(200, payload))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test", instrument_key_map=mapper)

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 1, 1, tzinfo=timezone.utc)
    res = await prov.get_candles("ABC", "1d", start, end)
    assert len(res) == 1
    assert res[0].instrument_id == "UPSTOX:ABC"
    # timezone preserved -> timestamp should have tzinfo
    assert res[0].timestamp.tzinfo is not None


def test_protocol_compliance():
    client = FakeClient(FakeResponse(200, {"status": "success", "data": {"candles": []}}))
    prov = UpstoxMarketDataProvider(client, base_url="https://api.test")
    from app.domain.market_data.provider import MarketDataProvider
    assert isinstance(prov, MarketDataProvider)
