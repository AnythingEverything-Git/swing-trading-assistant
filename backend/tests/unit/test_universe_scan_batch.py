"""Batch candle load keeps universe scans off the N×2 query path."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.scan.universe_scan_report_service import UniverseScanReportService
from app.domain.market_data import Candle
from app.domain.strategy.strategy import StrategyResult


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 2, 12, tzinfo=timezone.utc)


def _candle(symbol: str, day: int) -> Candle:
    return Candle(
        symbol=symbol,
        exchange="NSE",
        instrument_id=1,
        timeframe="1d",
        timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=1000,
    )


class BatchProvider:
    def __init__(self) -> None:
        self.batch_calls = 0
        self.single_calls = 0

    async def get_candles(self, symbol, timeframe, start, end):
        self.single_calls += 1
        return [_candle(symbol, i) for i in range(1, 25)]

    async def get_candles_for_symbols(self, symbols, timeframe, start, end):
        self.batch_calls += 1
        return {symbol: [_candle(symbol, i) for i in range(1, 25)] for symbol in symbols}


class StubStrategy:
    def evaluate(self, strategy_input):
        return StrategyResult(has_setup=False, candidate=None, evidence=None)

    def inspect_forming(self, strategy_input):
        return None


@pytest.mark.asyncio
async def test_universe_scan_uses_batch_candle_loader_once():
    from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService

    provider = BatchProvider()
    evaluation = StrategyEvaluationService(provider, StubStrategy())
    service = UniverseScanReportService(evaluation)
    report = await service.scan(("AAA", "BBB", "CCC"), "1d", START, END)
    assert report.symbols_scanned == 3
    assert report.no_setup_count == 3
    assert provider.batch_calls == 1
    assert provider.single_calls == 0
