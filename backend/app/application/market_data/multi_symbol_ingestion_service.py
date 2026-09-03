"""Sequential multi-symbol market-data ingestion orchestration.

Delegates each symbol to the existing MarketDataIngestionService. Does not
implement a second persistence pipeline, strategy logic, or concurrency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.domain.universe import StockUniverse


@dataclass(frozen=True)
class SymbolIngestionResult:
    """Per-symbol outcome of one multi-symbol ingestion pass."""

    symbol: str
    success: bool
    candles_fetched: int | None = None
    candles_persisted: int | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class MultiSymbolIngestionResult:
    """Deterministic summary of a sequential multi-symbol ingestion run."""

    timeframe: str
    start: datetime
    end: datetime
    results: tuple[SymbolIngestionResult, ...]

    @property
    def symbols_attempted(self) -> int:
        return len(self.results)

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.results if item.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for item in self.results if not item.success)


class MultiSymbolMarketDataIngestionService:
    """Orchestrate existing single-symbol ingestion across many NSE symbols."""

    def __init__(self, ingestion_service: MarketDataIngestionService) -> None:
        self.ingestion_service = ingestion_service

    async def ingest_symbols(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> MultiSymbolIngestionResult:
        results: list[SymbolIngestionResult] = []

        for symbol in symbols:
            try:
                fetched, persisted = await self.ingestion_service.ingest(
                    symbol,
                    timeframe,
                    start,
                    end,
                )
            except Exception as exc:
                # Catch Exception (not BaseException) so one symbol's operational
                # failure does not stop later symbols. Preserve diagnostics.
                results.append(
                    SymbolIngestionResult(
                        symbol=symbol,
                        success=False,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                continue

            results.append(
                SymbolIngestionResult(
                    symbol=symbol,
                    success=True,
                    candles_fetched=fetched,
                    candles_persisted=persisted,
                )
            )

        return MultiSymbolIngestionResult(
            timeframe=timeframe,
            start=start,
            end=end,
            results=tuple(results),
        )

    async def ingest_universe(
        self,
        universe: StockUniverse,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> MultiSymbolIngestionResult:
        snapshot = universe.get_snapshot()
        return await self.ingest_symbols(snapshot.symbols, timeframe, start, end)


__all__ = [
    "SymbolIngestionResult",
    "MultiSymbolIngestionResult",
    "MultiSymbolMarketDataIngestionService",
]
