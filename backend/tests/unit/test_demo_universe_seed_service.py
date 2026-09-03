"""Focused unit tests for explicit demo Nifty 500 universe seeding."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.application.market_data.demo_universe_seed_service import (
    DEFAULT_DEMO_SEED_LOOKBACK_DAYS,
    DemoUniverseSeedService,
    build_demo_nifty500_seed_service,
    default_demo_seed_range,
)
from app.application.market_data.multi_symbol_ingestion_service import (
    MultiSymbolIngestionResult,
    MultiSymbolMarketDataIngestionService,
    SymbolIngestionResult,
)
from app.domain.universe import StockUniverse, UniverseSnapshot
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider
from app.infrastructure.universe import Nifty500Universe


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 9, 1, tzinfo=timezone.utc)


class FakeStockUniverse:
    def __init__(self, symbols: tuple[str, ...] = ("AAA", "BBB", "CCC")) -> None:
        self._snapshot = UniverseSnapshot(
            name="NIFTY_500",
            version="test-v1",
            as_of=None,
            symbols=symbols,
        )
        self.snapshot_calls = 0

    def get_snapshot(self) -> UniverseSnapshot:
        self.snapshot_calls += 1
        return self._snapshot


class FakeMultiSymbolIngestion:
    def __init__(self, result: MultiSymbolIngestionResult) -> None:
        self.result = result
        self.calls: list[tuple[StockUniverse, str, datetime, datetime]] = []

    async def ingest_universe(
        self,
        universe: StockUniverse,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> MultiSymbolIngestionResult:
        self.calls.append((universe, timeframe, start, end))
        return self.result


@pytest.mark.asyncio
async def test_demo_seed_uses_universe_and_multi_symbol_ingestion():
    universe = FakeStockUniverse(("AAA", "BBB", "CCC"))
    ingestion_result = MultiSymbolIngestionResult(
        timeframe="1d",
        start=START,
        end=END,
        results=(
            SymbolIngestionResult("AAA", True, 10, 10),
            SymbolIngestionResult("BBB", False, error_type="UpstoxAPIError", error_message="boom"),
            SymbolIngestionResult("CCC", True, 8, 8),
        ),
    )
    multi = FakeMultiSymbolIngestion(ingestion_result)
    provider = DemoMarketDataProvider()
    service = DemoUniverseSeedService(universe, multi, provider)

    result = await service.seed(START, END)

    assert universe.snapshot_calls == 1
    assert len(multi.calls) == 1
    called_universe, timeframe, start, end = multi.calls[0]
    assert called_universe is universe
    assert [item.symbol for item in result.ingestion.results] == ["AAA", "BBB", "CCC"]
    assert timeframe == "1d"
    assert start == START and end == END
    assert result.universe_name == "NIFTY_500"
    assert result.universe_version == "test-v1"
    assert result.provider_type == "DemoMarketDataProvider"
    assert result.symbols_attempted == 3
    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.candles_fetched == 18
    assert result.candles_persisted == 18
    assert result.ingestion.results[1].error_message == "boom"

def test_demo_seed_rejects_non_demo_provider():
    universe = FakeStockUniverse()
    multi = FakeMultiSymbolIngestion(
        MultiSymbolIngestionResult(timeframe="1d", start=START, end=END, results=())
    )
    with pytest.raises(TypeError, match="DemoMarketDataProvider"):
        DemoUniverseSeedService(universe, multi, MockMarketDataProvider())  # type: ignore[arg-type]


def test_build_demo_nifty500_seed_service_wires_expected_components():
    session = SimpleNamespace()
    service = build_demo_nifty500_seed_service(session)

    assert isinstance(service.universe, Nifty500Universe)
    assert isinstance(service.provider, DemoMarketDataProvider)
    assert type(service.provider).__name__ == "DemoMarketDataProvider"
    assert type(service.provider).__name__ != "UpstoxMarketDataProvider"
    assert isinstance(service.multi_symbol_ingestion, MultiSymbolMarketDataIngestionService)
    assert service.multi_symbol_ingestion.ingestion_service.provider is service.provider
    snapshot = service.universe.get_snapshot()
    assert snapshot.name == "NIFTY_500"
    assert len(snapshot.symbols) == 498


def test_default_demo_seed_range_is_about_nine_months():
    start, end = default_demo_seed_range(now=datetime(2024, 9, 1, tzinfo=timezone.utc))
    assert end == datetime(2024, 9, 1, tzinfo=timezone.utc)
    assert (end - start).days == DEFAULT_DEMO_SEED_LOOKBACK_DAYS
