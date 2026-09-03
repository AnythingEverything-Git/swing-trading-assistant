"""Explicitly seed deterministic demo candles for the Nifty 500 universe.

Development/demo only. Refuses to run when Settings.environment == "production".
Does not change production Upstox provider wiring.

Usage (from the backend directory):

    python scripts/seed_demo_nifty500.py
    python scripts/seed_demo_nifty500.py --start 2024-01-01 --end 2024-09-01
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.market_data.demo_universe_seed_service import (
    build_demo_nifty500_seed_service,
    default_demo_seed_range,
)
from app.core.config import get_settings
from app.infrastructure.database.session import create_engine, create_sessionmaker


def _parse_iso_date(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed Nifty 500 universe with DemoMarketDataProvider 1d candles."
    )
    parser.add_argument(
        "--start",
        type=_parse_iso_date,
        default=None,
        help="Inclusive UTC start date (YYYY-MM-DD). Default: ~9 months before end.",
    )
    parser.add_argument(
        "--end",
        type=_parse_iso_date,
        default=None,
        help="Inclusive UTC end date (YYYY-MM-DD). Default: today UTC.",
    )
    return parser


async def seed_demo_nifty500(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
):
    settings = get_settings()
    if settings.environment.strip().lower() == "production":
        raise SystemExit("Refusing to seed demo data: environment is production")

    default_start, default_end = default_demo_seed_range()
    resolved_end = end or default_end
    resolved_start = start or default_start
    if start is None and end is not None:
        resolved_start = resolved_end - (default_end - default_start)
    if start is not None and end is None:
        resolved_end = default_end
    if resolved_start > resolved_end:
        raise SystemExit("start must be <= end")

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            service = build_demo_nifty500_seed_service(session)
            result = await service.seed(resolved_start, resolved_end, timeframe="1d")
            await session.commit()
    finally:
        await engine.dispose()

    return result


def main() -> None:
    args = _build_arg_parser().parse_args()
    result = asyncio.run(seed_demo_nifty500(start=args.start, end=args.end))

    failed = [item for item in result.ingestion.results if not item.success]
    print("Demo Nifty 500 seed complete")
    print(f"  universe={result.universe_name} version={result.universe_version}")
    print(f"  provider={result.provider_type} timeframe={result.timeframe}")
    print(f"  range={result.start.date().isoformat()} .. {result.end.date().isoformat()}")
    print(f"  symbols_attempted={result.symbols_attempted}")
    print(f"  success={result.success_count} failure={result.failure_count}")
    print(f"  candles_fetched={result.candles_fetched} candles_persisted={result.candles_persisted}")
    if failed:
        print("  failed_symbols:")
        for item in failed:
            print(f"    - {item.symbol}: {item.error_type}: {item.error_message}")


if __name__ == "__main__":
    main()
