from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.domain.market_data import Candle
from app.domain.market_data.provider import MarketDataProvider


class FakeProvider(MarketDataProvider):
    def __init__(self, candles=None, raise_exc: Exception | None = None):
        self._candles = candles or []
        self._raise = raise_exc

    async def get_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime):
        if self._raise:
            raise self._raise
        return [c for c in self._candles if c.symbol == symbol and c.timeframe == timeframe and start <= c.timestamp <= end]


class FakeInstrumentRepo:
    def __init__(self, id_seq=1):
        self.created = []
        self.id_seq = id_seq

    async def get_or_create(self, symbol: str, name=None, exchange=None, metadata=None):
        # return a simple object with `id` attribute
        obj = type("Inst", (), {})()
        obj.id = self.id_seq
        self.id_seq += 1
        self.created.append((symbol, exchange))
        return obj


class FakeCandleRepo:
    def __init__(self):
        self.saved = []

    async def save_many(self, candles):
        self.saved.append(candles)


@pytest.mark.asyncio
async def test_successful_ingestion():
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    c1 = Candle("TST", "EX", None, "1d", ts, Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), 100)
    c2 = Candle("TST", "EX", None, "1d", ts + timedelta(days=1), Decimal("100"), Decimal("102"), Decimal("98"), Decimal("101"), 200)

    prov = FakeProvider(candles=[c1, c2])
    inst_repo = FakeInstrumentRepo()
    candle_repo = FakeCandleRepo()

    svc = MarketDataIngestionService(prov, inst_repo, candle_repo)
    count = await svc.ingest("TST", "1d", ts, ts + timedelta(days=1))

    assert count == 2
    assert len(candle_repo.saved) == 1
    saved = candle_repo.saved[0]
    assert all(r["instrument_id"] == 1 for r in saved)
    assert saved[0]["timeframe"] == "1d"


@pytest.mark.asyncio
async def test_provider_returns_no_candles():
    prov = FakeProvider(candles=[])
    inst_repo = FakeInstrumentRepo()
    candle_repo = FakeCandleRepo()
    svc = MarketDataIngestionService(prov, inst_repo, candle_repo)

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    count = await svc.ingest("TST", "1d", start, end)
    assert count == 0
    assert inst_repo.created == []
    assert candle_repo.saved == []


@pytest.mark.asyncio
async def test_instrument_reused_and_mapping():
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    c1 = Candle("ABC", "EX", None, "1d", ts, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), 50)
    prov = FakeProvider(candles=[c1])

    inst_repo = FakeInstrumentRepo(id_seq=42)
    candle_repo = FakeCandleRepo()
    svc = MarketDataIngestionService(prov, inst_repo, candle_repo)

    count = await svc.ingest("ABC", "1d", ts, ts)
    assert count == 1
    assert inst_repo.created[0][0] == "ABC"
    saved = candle_repo.saved[0]
    assert saved[0]["instrument_id"] == 42


@pytest.mark.asyncio
async def test_provider_exception_propagates():
    prov = FakeProvider(raise_exc=RuntimeError("boom"))
    inst_repo = FakeInstrumentRepo()
    candle_repo = FakeCandleRepo()
    svc = MarketDataIngestionService(prov, inst_repo, candle_repo)

    with pytest.raises(RuntimeError):
        await svc.ingest("X", "1d", datetime.now(timezone.utc), datetime.now(timezone.utc))


def test_invalid_date_range_raises():
    prov = FakeProvider()
    inst_repo = FakeInstrumentRepo()
    candle_repo = FakeCandleRepo()
    svc = MarketDataIngestionService(prov, inst_repo, candle_repo)

    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(svc.ingest("X", "1d", datetime(2021, 1, 2, tzinfo=timezone.utc), datetime(2021, 1, 1, tzinfo=timezone.utc)))
