"""Focused unit tests for sequential multi-symbol market-data ingestion."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.application.market_data.multi_symbol_ingestion_service import (
    MultiSymbolMarketDataIngestionService,
)
from app.domain.universe import StockUniverse, UniverseSnapshot
from app.infrastructure.market_data.upstox_provider import UpstoxAPIError


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 3, 1, tzinfo=timezone.utc)


class FakeIngestionService:
    """Records ingest calls and returns configured per-symbol outcomes."""

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


class FakeStockUniverse:
    def __init__(self, symbols: tuple[str, ...]) -> None:
        self._snapshot = UniverseSnapshot(
            name="TEST_UNIVERSE",
            version="v1",
            as_of=None,
            symbols=symbols,
        )
        self.snapshot_calls = 0

    def get_snapshot(self) -> UniverseSnapshot:
        self.snapshot_calls += 1
        return self._snapshot


@pytest.mark.asyncio
async def test_ingest_symbols_calls_single_symbol_ingest_once_each():
    ingestion = FakeIngestionService(
        {
            "AAA": (10, 10),
            "BBB": (5, 5),
            "CCC": (0, 0),
        }
    )
    service = MultiSymbolMarketDataIngestionService(ingestion)

    result = await service.ingest_symbols(["AAA", "BBB", "CCC"], "1d", START, END)

    assert [call[0] for call in ingestion.calls] == ["AAA", "BBB", "CCC"]
    assert all(call[1] == "1d" and call[2] == START and call[3] == END for call in ingestion.calls)
    assert result.symbols_attempted == 3
    assert result.success_count == 3
    assert result.failure_count == 0
    assert result.results[0].candles_fetched == 10
    assert result.results[0].candles_persisted == 10
    assert result.results[2].candles_fetched == 0
    assert result.results[2].candles_persisted == 0
    assert result.results[2].success is True


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_later_symbols_and_retains_diagnostics():
    ingestion = FakeIngestionService(
        {
            "AAA": (8, 8),
            "BBB": UpstoxAPIError("Instrument mapping missing for symbol: BBB"),
            "CCC": (3, 2),
        }
    )
    service = MultiSymbolMarketDataIngestionService(ingestion)

    result = await service.ingest_symbols(["AAA", "BBB", "CCC"], "1d", START, END)

    assert [call[0] for call in ingestion.calls] == ["AAA", "BBB", "CCC"]
    assert result.success_count == 2
    assert result.failure_count == 1

    failed = result.results[1]
    assert failed.symbol == "BBB"
    assert failed.success is False
    assert failed.candles_fetched is None
    assert failed.candles_persisted is None
    assert failed.error_type == "UpstoxAPIError"
    assert "Instrument mapping missing for symbol: BBB" in (failed.error_message or "")

    assert result.results[0].success is True
    assert result.results[2].success is True
    assert result.results[2].candles_fetched == 3
    assert result.results[2].candles_persisted == 2


@pytest.mark.asyncio
async def test_ingest_universe_uses_stock_universe_snapshot_symbols():
    universe: StockUniverse = FakeStockUniverse(("AAA", "BBB"))
    ingestion = FakeIngestionService({"AAA": (1, 1), "BBB": (2, 2)})
    service = MultiSymbolMarketDataIngestionService(ingestion)

    result = await service.ingest_universe(universe, "1d", START, END)

    assert universe.snapshot_calls == 1
    assert [call[0] for call in ingestion.calls] == ["AAA", "BBB"]
    assert result.symbols_attempted == 2
    assert result.success_count == 2
    assert [item.symbol for item in result.results] == ["AAA", "BBB"]


@pytest.mark.asyncio
async def test_empty_symbol_list_returns_empty_results():
    ingestion = FakeIngestionService({})
    service = MultiSymbolMarketDataIngestionService(ingestion)

    result = await service.ingest_symbols([], "1d", START, END)

    assert ingestion.calls == []
    assert result.results == ()
    assert result.symbols_attempted == 0
