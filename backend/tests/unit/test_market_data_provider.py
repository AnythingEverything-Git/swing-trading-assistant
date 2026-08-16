from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.domain.market_data import Candle
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider
from app.domain.market_data.provider import MarketDataProvider


def test_candle_dataclass():
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    c = Candle(
        symbol="TST",
        exchange="EX",
        instrument_id=123,
        timeframe="1d",
        timestamp=ts,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
    )
    assert c.symbol == "TST"
    assert c.timestamp == ts
    assert c.open == Decimal("100")


@pytest.mark.asyncio
async def test_mock_provider_generates_and_filters():
    prov = MockMarketDataProvider()
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=2)

    candles = await prov.get_candles("TST", "1d", start, end)
    assert len(candles) == 3
    # symbol & timeframe
    for c in candles:
        assert c.symbol == "TST"
        assert c.timeframe == "1d"

    # range filtering
    sub = await prov.get_candles("TST", "1d", start + timedelta(days=1), end)
    assert len(sub) == 2

    # generated provider returns deterministic candles for any symbol
    empty = await prov.get_candles("NOPE", "1d", start, end)
    assert isinstance(empty, list)


@pytest.mark.asyncio
async def test_mock_provider_with_preseeded_candles():
    ts = datetime(2021, 6, 1, tzinfo=timezone.utc)
    c1 = Candle("A", "EX", None, "1d", ts, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), 100)
    c2 = Candle("B", "EX", None, "1d", ts + timedelta(days=1), Decimal("20"), Decimal("22"), Decimal("19"), Decimal("21"), 200)
    prov = MockMarketDataProvider(candles=[c1, c2])

    res_a = await prov.get_candles("A", "1d", ts, ts)
    assert len(res_a) == 1 and res_a[0].symbol == "A"

    res_b = await prov.get_candles("B", "1d", ts, ts + timedelta(days=2))
    assert len(res_b) == 1 and res_b[0].symbol == "B"

    # no-match returns empty when provider was pre-seeded with other symbols
    none = await prov.get_candles("C", "1d", ts, ts + timedelta(days=2))
    assert none == []


def test_provider_protocol_compliance():
    prov = MockMarketDataProvider()
    assert isinstance(prov, MarketDataProvider)
