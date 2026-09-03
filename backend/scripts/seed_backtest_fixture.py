"""Seed the deterministic backtest candle fixture into the configured database.

Development/test only. Refuses to run when Settings.environment == "production".

Usage (from the backend directory):

    python -m scripts.seed_backtest_fixture
    # or
    python scripts/seed_backtest_fixture.py
"""
from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

# Allow running as a script from backend/ or repo root without install.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.core.config import get_settings
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.session import create_engine, create_sessionmaker
from app.infrastructure.market_data.deterministic_setup_series import (
    build_two_independent_setup_series,
)
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider


async def seed_backtest_fixture() -> tuple[int, int]:
    settings = get_settings()
    if settings.environment.strip().lower() == "production":
        raise SystemExit("Refusing to seed: environment is production")

    series = build_two_independent_setup_series()
    if not series:
        raise SystemExit("Fixture series is empty")

    start = series[0].timestamp
    end = series[-1].timestamp
    provider = MockMarketDataProvider(candles=series)

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            svc = MarketDataIngestionService(
                provider,
                InstrumentRepository(session),
                CandleRepository(session),
            )
            fetched, persisted = await svc.ingest("TST", "1d", start, end)
            await session.commit()
    finally:
        await engine.dispose()

    return fetched, persisted


def _run_async(coro):
    """Run a coroutine with a psycopg-compatible event loop on Windows."""
    if sys.platform.startswith("win"):
        # psycopg async requires SelectorEventLoop; Windows defaults to ProactorEventLoop.
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def main() -> None:
    fetched, persisted = _run_async(seed_backtest_fixture())
    print(
        f"Seeded backtest fixture TST/1d: "
        f"candles_fetched={fetched} candles_persisted={persisted}"
    )


if __name__ == "__main__":
    main()
