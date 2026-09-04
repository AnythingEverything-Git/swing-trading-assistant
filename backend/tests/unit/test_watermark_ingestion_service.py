"""Unit tests for per-symbol watermark market-data ingestion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.application.market_data.demo_universe_seed_service import DEFAULT_DEMO_SEED_LOOKBACK_DAYS
from app.application.market_data.watermark_ingestion_service import (
    WatermarkIngestionService,
    compute_watermark_window,
)
from app.domain.universe import UniverseSnapshot
from app.infrastructure.market_data.upstox_provider import UpstoxAPIError


END = datetime(2026, 9, 4, tzinfo=timezone.utc)


class FakeIngestionService:
    def __init__(self, outcomes: dict[str, tuple[int, int] | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    async def ingest(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> tuple[int, int]:
        self.calls.append((symbol, timeframe, start, end))
        outcome = self.outcomes[symbol]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeInstrumentRepo:
    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self._next = 1

    async def get_or_create(self, symbol: str, **kwargs):
        if symbol not in self._ids:
            self._ids[symbol] = self._next
            self._next += 1
        return SimpleNamespace(id=self._ids[symbol], symbol=symbol)


class FakeCandleRepo:
    def __init__(self, latest_by_instrument: dict[int, datetime | None]) -> None:
        self.latest_by_instrument = latest_by_instrument

    async def get_latest(self, instrument_id: int, timeframe: str = "1d"):
        ts = self.latest_by_instrument.get(instrument_id)
        if ts is None:
            return None
        return SimpleNamespace(timestamp=ts, timeframe=timeframe)


class FakeStockUniverse:
    def __init__(self, symbols: tuple[str, ...]) -> None:
        self._snapshot = UniverseSnapshot(
            name="TEST",
            version="v1",
            as_of=None,
            symbols=symbols,
        )

    def get_snapshot(self) -> UniverseSnapshot:
        return self._snapshot


def test_compute_window_from_yesterday():
    latest = END - timedelta(days=1)
    window = compute_watermark_window(latest, end=END)
    assert window == (END, END)


def test_compute_window_already_current_skips():
    assert compute_watermark_window(END, end=END) is None


def test_compute_window_no_history_uses_lookback():
    window = compute_watermark_window(None, end=END, lookback_days=10)
    assert window is not None
    start, resolved_end = window
    assert resolved_end == END
    assert start == END - timedelta(days=10)
    assert DEFAULT_DEMO_SEED_LOOKBACK_DAYS == 270


@pytest.mark.asyncio
async def test_ingest_symbols_yesterday_fetches_today_only():
    instruments = FakeInstrumentRepo()
    # Pre-assign AAA → id 1
    await instruments.get_or_create("AAA")
    candles = FakeCandleRepo({1: END - timedelta(days=1)})
    ingestion = FakeIngestionService({"AAA": (1, 1)})
    service = WatermarkIngestionService(ingestion, instruments, candles)

    result = await service.ingest_symbols(["AAA"], "1d", END)

    assert result.success_count == 1
    assert result.skipped_count == 0
    assert ingestion.calls == [("AAA", "1d", END, END)]
    assert result.results[0].candles_persisted == 1


@pytest.mark.asyncio
async def test_ingest_symbols_already_current_skipped():
    instruments = FakeInstrumentRepo()
    await instruments.get_or_create("AAA")
    candles = FakeCandleRepo({1: END})
    ingestion = FakeIngestionService({})
    service = WatermarkIngestionService(ingestion, instruments, candles)

    result = await service.ingest_symbols(["AAA"], "1d", END)

    assert ingestion.calls == []
    assert result.skipped_count == 1
    assert result.success_count == 0
    assert result.results[0].skipped is True
    assert result.results[0].success is True


@pytest.mark.asyncio
async def test_ingest_symbols_no_candles_uses_lookback():
    instruments = FakeInstrumentRepo()
    candles = FakeCandleRepo({})
    ingestion = FakeIngestionService({"BBB": (5, 5)})
    service = WatermarkIngestionService(ingestion, instruments, candles, lookback_days=30)

    result = await service.ingest_symbols(["BBB"], "1d", END)

    assert result.success_count == 1
    assert len(ingestion.calls) == 1
    assert ingestion.calls[0][0] == "BBB"
    assert ingestion.calls[0][2] == END - timedelta(days=30)
    assert ingestion.calls[0][3] == END


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_later_symbols():
    instruments = FakeInstrumentRepo()
    candles = FakeCandleRepo({})
    ingestion = FakeIngestionService(
        {
            "AAA": (2, 2),
            "BBB": UpstoxAPIError("missing"),
            "CCC": (1, 1),
        }
    )
    service = WatermarkIngestionService(ingestion, instruments, candles, lookback_days=7)

    result = await service.ingest_symbols(["AAA", "BBB", "CCC"], "1d", END)

    assert [c[0] for c in ingestion.calls] == ["AAA", "BBB", "CCC"]
    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.results[1].error_type == "UpstoxAPIError"


@pytest.mark.asyncio
async def test_ingest_universe_uses_snapshot():
    universe = FakeStockUniverse(("AAA", "BBB"))
    instruments = FakeInstrumentRepo()
    candles = FakeCandleRepo({})
    ingestion = FakeIngestionService({"AAA": (1, 1), "BBB": (1, 1)})
    service = WatermarkIngestionService(ingestion, instruments, candles, lookback_days=3)

    result = await service.ingest_universe(universe, "1d", END)

    assert result.symbols_attempted == 2
    assert result.success_count == 2
