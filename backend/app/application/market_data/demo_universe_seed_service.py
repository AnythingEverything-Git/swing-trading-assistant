"""Explicit demo-only seeding of a StockUniverse via DemoMarketDataProvider.

Composes existing Nifty500Universe / DemoMarketDataProvider /
MultiSymbolMarketDataIngestionService. Does not alter production Upstox wiring.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.application.market_data.multi_symbol_ingestion_service import (
    MultiSymbolIngestionResult,
    MultiSymbolMarketDataIngestionService,
)
from app.domain.universe import StockUniverse, UniverseSnapshot
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider
from app.infrastructure.universe import Nifty500Universe
from sqlalchemy.ext.asyncio import AsyncSession


DEFAULT_DEMO_SEED_LOOKBACK_DAYS = 270  # ~9 months of calendar days for 1d history


@dataclass(frozen=True)
class DemoUniverseSeedResult:
    """Summary of an explicit demo universe seed run."""

    universe_name: str
    universe_version: str
    timeframe: str
    start: datetime
    end: datetime
    provider_type: str
    ingestion: MultiSymbolIngestionResult

    @property
    def symbols_attempted(self) -> int:
        return self.ingestion.symbols_attempted

    @property
    def success_count(self) -> int:
        return self.ingestion.success_count

    @property
    def failure_count(self) -> int:
        return self.ingestion.failure_count

    @property
    def candles_fetched(self) -> int:
        return sum(item.candles_fetched or 0 for item in self.ingestion.results if item.success)

    @property
    def candles_persisted(self) -> int:
        return sum(item.candles_persisted or 0 for item in self.ingestion.results if item.success)


def default_demo_seed_range(*, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Default ~9-month UTC daily window ending today (UTC date)."""
    current = now or datetime.now(timezone.utc)
    end = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
    start = end - timedelta(days=DEFAULT_DEMO_SEED_LOOKBACK_DAYS)
    return start, end


class DemoUniverseSeedService:
    """Seed persisted candles for a universe using DemoMarketDataProvider only."""

    def __init__(
        self,
        universe: StockUniverse,
        multi_symbol_ingestion: MultiSymbolMarketDataIngestionService,
        provider: DemoMarketDataProvider,
    ) -> None:
        if not isinstance(provider, DemoMarketDataProvider):
            raise TypeError("DemoUniverseSeedService requires DemoMarketDataProvider")
        self.universe = universe
        self.multi_symbol_ingestion = multi_symbol_ingestion
        self.provider = provider

    async def seed(
        self,
        start: datetime,
        end: datetime,
        *,
        timeframe: str = "1d",
    ) -> DemoUniverseSeedResult:
        if start > end:
            raise ValueError("start must be <= end")
        snapshot: UniverseSnapshot = self.universe.get_snapshot()
        ingestion = await self.multi_symbol_ingestion.ingest_universe(
            self.universe,
            timeframe,
            start,
            end,
        )
        return DemoUniverseSeedResult(
            universe_name=snapshot.name,
            universe_version=snapshot.version,
            timeframe=timeframe,
            start=start,
            end=end,
            provider_type=type(self.provider).__name__,
            ingestion=ingestion,
        )


def build_demo_nifty500_seed_service(session: AsyncSession) -> DemoUniverseSeedService:
    """Wire Nifty500Universe + DemoMarketDataProvider + multi-symbol ingestion for one session."""
    provider = DemoMarketDataProvider()
    ingestion = MarketDataIngestionService(
        provider,
        InstrumentRepository(session),
        CandleRepository(session),
    )
    multi = MultiSymbolMarketDataIngestionService(ingestion)
    return DemoUniverseSeedService(
        universe=Nifty500Universe(),
        multi_symbol_ingestion=multi,
        provider=provider,
    )


__all__ = [
    "DEFAULT_DEMO_SEED_LOOKBACK_DAYS",
    "DemoUniverseSeedResult",
    "DemoUniverseSeedService",
    "build_demo_nifty500_seed_service",
    "default_demo_seed_range",
]
