"""Explicitly seed deterministic demo candles for the Nifty 500 universe.

Development/demo only. Refuses to run when Settings.environment == "production".
Does not change production Upstox provider wiring.

Usage (from the backend directory):

    python scripts/seed_demo_nifty500.py
    python scripts/seed_demo_nifty500.py --start 2024-01-01 --end 2024-09-01
    python scripts/seed_demo_nifty500.py --to-today
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
    parser.add_argument(
        "--to-today",
        action="store_true",
        help=(
            "Demo refresh: end at today UTC and re-seed the full window "
            "(~9 months unless --start is set). Prefer this over partial watermark "
            "ingest — demo OHLC is generated for the requested range."
        ),
    )
    return parser


async def seed_demo_nifty500(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    to_today: bool = False,
):
    settings = get_settings()
    if settings.environment.strip().lower() == "production":
        raise SystemExit("Refusing to seed demo data: environment is production")

    default_start, default_end = default_demo_seed_range()
    if to_today:
        resolved_end = default_end
        resolved_start = start or default_start
    else:
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
    args = _build_arg_parser().parse_args()
    if args.to_today and args.end is not None:
        raise SystemExit("Use either --to-today or --end, not both")
    result = _run_async(
        seed_demo_nifty500(start=args.start, end=args.end, to_today=args.to_today)
    )

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
