"""Refresh persisted 1d candles from the configured market-data source.

Demo (default):
    python scripts/refresh_market_data.py --universe NIFTY_50

Live watermark (incremental; default when MARKET_DATA_SOURCE=upstox):
    MARKET_DATA_SOURCE=upstox UPSTOX_ACCESS_TOKEN=... python scripts/refresh_market_data.py --mode watermark

Full window (explicit range or demo default ~9 months):
    python scripts/refresh_market_data.py --mode full --start 2025-01-01 --end 2026-09-04
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.market_data.demo_universe_seed_service import (
    DemoUniverseSeedService,
    default_demo_seed_range,
)
from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.application.market_data.multi_symbol_ingestion_service import MultiSymbolMarketDataIngestionService
from app.application.market_data.refresh_scheduler import utc_today_end
from app.application.market_data.watermark_ingestion_service import WatermarkIngestionService
from app.core.config import get_settings
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.session import create_engine, create_sessionmaker
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider
from app.infrastructure.market_data.factory import UpstoxProviderFactory
from app.infrastructure.market_data.source import normalize_market_data_source
from app.infrastructure.universe import get_universe


def _parse_iso_date(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def _default_mode(source: str) -> str:
    return "watermark" if source == "upstox" else "full"


async def refresh(
    *,
    universe_name: str,
    mode: str,
    start: datetime | None,
    end: datetime | None,
) -> None:
    settings = get_settings()
    source = normalize_market_data_source(settings.market_data_source)
    resolved_mode = mode or _default_mode(source)
    default_start, default_end = default_demo_seed_range()
    resolved_end = end or (utc_today_end() if resolved_mode == "watermark" else default_end)
    resolved_start = start or default_start
    universe = get_universe(universe_name)

    if resolved_mode == "watermark" and source == "demo":
        raise SystemExit(
            "Refusing --mode watermark with MARKET_DATA_SOURCE=demo. "
            "Use --mode full (or omit --mode) to re-seed the demo window."
        )

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            if source == "demo":
                if settings.environment.strip().lower() == "production":
                    raise SystemExit("Refusing demo seed: environment is production")
                provider = DemoMarketDataProvider()
                ingestion = MarketDataIngestionService(
                    provider,
                    InstrumentRepository(session),
                    CandleRepository(session),
                )
                service = DemoUniverseSeedService(
                    universe=universe,
                    multi_symbol_ingestion=MultiSymbolMarketDataIngestionService(ingestion),
                    provider=provider,
                )
                result = await service.seed(resolved_start, resolved_end, timeframe="1d")
                await session.commit()
                print(f"Demo refresh complete source=demo universe={universe_name} mode=full")
                print(f"  success={result.success_count} failure={result.failure_count}")
                print(f"  candles_persisted={result.candles_persisted}")
                return

            factory = UpstoxProviderFactory()
            provider = await factory.startup()
            try:
                instrument_repo = InstrumentRepository(session)
                candle_repo = CandleRepository(session)
                ingestion = MarketDataIngestionService(provider, instrument_repo, candle_repo)
                if resolved_mode == "watermark":
                    watermark = WatermarkIngestionService(ingestion, instrument_repo, candle_repo)
                    result = await watermark.ingest_universe(universe, "1d", resolved_end)
                    await session.commit()
                    print(f"Live refresh complete source=upstox universe={universe_name} mode=watermark")
                    print(
                        f"  success={result.success_count} skipped={result.skipped_count} "
                        f"failure={result.failure_count}"
                    )
                    print(f"  candles_persisted={result.candles_persisted}")
                    failed = [item for item in result.results if not item.success and not item.skipped]
                else:
                    multi = MultiSymbolMarketDataIngestionService(ingestion)
                    result = await multi.ingest_universe(
                        universe, "1d", resolved_start, resolved_end
                    )
                    await session.commit()
                    print(f"Live refresh complete source=upstox universe={universe_name} mode=full")
                    print(f"  success={result.success_count} failure={result.failure_count}")
                    failed = [item for item in result.results if not item.success]
                if failed:
                    print("  failed_symbols:")
                    for item in failed[:40]:
                        print(f"    - {item.symbol}: {item.error_type}: {item.error_message}")
                    if len(failed) > 40:
                        print(f"    ... {len(failed) - 40} more")
            finally:
                await factory.shutdown()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh candles from MARKET_DATA_SOURCE.")
    parser.add_argument("--universe", default="NIFTY_500")
    parser.add_argument(
        "--mode",
        choices=("watermark", "full"),
        default=None,
        help="watermark=incremental from last candle (upstox default); full=explicit/demo window",
    )
    parser.add_argument("--start", type=_parse_iso_date, default=None)
    parser.add_argument("--end", type=_parse_iso_date, default=None)
    args = parser.parse_args()
    _run_async(
        refresh(
            universe_name=args.universe,
            mode=args.mode,
            start=args.start,
            end=args.end,
        )
    )


if __name__ == "__main__":
    main()
