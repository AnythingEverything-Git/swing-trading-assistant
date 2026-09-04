"""Per-symbol watermark (incremental) market-data ingestion.

For each symbol, fetch only from the day after the latest persisted 1d candle
through ``end``. Symbols with no history use a lookback fallback. Already-current
symbols are skipped (not failures).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.application.market_data.demo_universe_seed_service import DEFAULT_DEMO_SEED_LOOKBACK_DAYS
from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.domain.universe import StockUniverse
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository


@dataclass(frozen=True)
class WatermarkSymbolResult:
    """Per-symbol outcome of one watermark ingestion pass."""

    symbol: str
    success: bool
    skipped: bool = False
    start: datetime | None = None
    end: datetime | None = None
    candles_fetched: int | None = None
    candles_persisted: int | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class WatermarkIngestionResult:
    """Summary of a watermark multi-symbol run."""

    timeframe: str
    end: datetime
    results: tuple[WatermarkSymbolResult, ...]

    @property
    def symbols_attempted(self) -> int:
        return len(self.results)

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.results if item.skipped)

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.results if item.success and not item.skipped)

    @property
    def failure_count(self) -> int:
        return sum(1 for item in self.results if not item.success and not item.skipped)

    @property
    def candles_persisted(self) -> int:
        return sum(item.candles_persisted or 0 for item in self.results if item.success)


def compute_watermark_window(
    latest_ts: datetime | None,
    *,
    end: datetime,
    lookback_days: int = DEFAULT_DEMO_SEED_LOOKBACK_DAYS,
) -> tuple[datetime, datetime] | None:
    """Return (start, end) to fetch, or None when the symbol is already current."""
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    else:
        end = end.astimezone(timezone.utc)

    if latest_ts is None:
        start = end - timedelta(days=lookback_days)
    else:
        latest = latest_ts if latest_ts.tzinfo else latest_ts.replace(tzinfo=timezone.utc)
        latest = latest.astimezone(timezone.utc)
        latest_day = latest.date()
        start = datetime(latest_day.year, latest_day.month, latest_day.day, tzinfo=timezone.utc) + timedelta(
            days=1
        )

    if start > end:
        return None
    return start, end


class WatermarkIngestionService:
    """Incremental ingest from each symbol's last persisted 1d candle."""

    def __init__(
        self,
        ingestion_service: MarketDataIngestionService,
        instrument_repo: InstrumentRepository,
        candle_repo: CandleRepository,
        *,
        lookback_days: int = DEFAULT_DEMO_SEED_LOOKBACK_DAYS,
    ) -> None:
        self.ingestion_service = ingestion_service
        self.instrument_repo = instrument_repo
        self.candle_repo = candle_repo
        self.lookback_days = lookback_days

    async def ingest_symbols(
        self,
        symbols: Sequence[str],
        timeframe: str,
        end: datetime,
    ) -> WatermarkIngestionResult:
        results: list[WatermarkSymbolResult] = []

        for symbol in symbols:
            try:
                inst = await self.instrument_repo.get_or_create(symbol=symbol)
                latest = await self.candle_repo.get_latest(inst.id, timeframe)
                latest_ts = latest.timestamp if latest is not None else None
                window = compute_watermark_window(
                    latest_ts,
                    end=end,
                    lookback_days=self.lookback_days,
                )
                if window is None:
                    results.append(
                        WatermarkSymbolResult(
                            symbol=symbol,
                            success=True,
                            skipped=True,
                            end=end,
                        )
                    )
                    continue

                start, resolved_end = window
                fetched, persisted = await self.ingestion_service.ingest(
                    symbol,
                    timeframe,
                    start,
                    resolved_end,
                )
            except Exception as exc:
                results.append(
                    WatermarkSymbolResult(
                        symbol=symbol,
                        success=False,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                continue

            results.append(
                WatermarkSymbolResult(
                    symbol=symbol,
                    success=True,
                    start=start,
                    end=resolved_end,
                    candles_fetched=fetched,
                    candles_persisted=persisted,
                )
            )

        return WatermarkIngestionResult(
            timeframe=timeframe,
            end=end,
            results=tuple(results),
        )

    async def ingest_universe(
        self,
        universe: StockUniverse,
        timeframe: str,
        end: datetime,
    ) -> WatermarkIngestionResult:
        snapshot = universe.get_snapshot()
        return await self.ingest_symbols(snapshot.symbols, timeframe, end)


__all__ = [
    "WatermarkSymbolResult",
    "WatermarkIngestionResult",
    "WatermarkIngestionService",
    "compute_watermark_window",
]
