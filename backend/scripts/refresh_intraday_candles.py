"""Backfill / catch-up Upstox 1-minute candles into Postgres.

Upstox historical 1m windows are limited (~1 month per request). This script
chunks by calendar month and walks the universe sequentially with a short pause.

Examples (from backend/):

    # Last ~20 calendar days for Nifty 50 (default)
    python scripts/refresh_intraday_candles.py

    # Explicit range
    python scripts/refresh_intraday_candles.py --universe NIFTY_50 --start 2026-08-01 --end 2026-09-07

    # Today only via intraday endpoint + persist
    python scripts/refresh_intraday_candles.py --mode today

    # Incremental watermark (next bar after latest 1m)
    python scripts/refresh_intraday_candles.py --mode watermark --timeframe 1m --limit-symbols 5

Requires MARKET_DATA_SOURCE=upstox (or demo for synthetic minute seed):

    # Seed a few demo symbols' minute bars into Postgres (no Upstox)
    MARKET_DATA_SOURCE=demo python scripts/refresh_intraday_candles.py --mode demo --limit-symbols 5
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.core.config import get_settings
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.session import create_engine, create_sessionmaker
from app.infrastructure.market_data.factory import UpstoxProviderFactory
from app.infrastructure.market_data.source import normalize_market_data_source
from app.infrastructure.universe import get_universe

IST = ZoneInfo("Asia/Kolkata")


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def _month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        last_day = monthrange(cur.year, cur.month)[1]
        chunk_start = max(start, cur)
        chunk_end = min(end, date(cur.year, cur.month, last_day))
        chunks.append((chunk_start, chunk_end))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return chunks


def _as_utc_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


async def _ingest_range(
    *,
    universe_name: str,
    start: date,
    end: date,
    pause_s: float,
    limit_symbols: int | None,
) -> None:
    settings = get_settings()
    if normalize_market_data_source(settings.market_data_source) != "upstox":
        raise SystemExit("Set MARKET_DATA_SOURCE=upstox for 1m backfill")

    universe = get_universe(universe_name)
    symbols = list(universe.get_snapshot().symbols)
    if limit_symbols is not None:
        symbols = symbols[: max(1, limit_symbols)]

    chunks = _month_chunks(start, end)
    factory = UpstoxProviderFactory()
    provider = await factory.startup()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    fetched_total = 0
    persisted_total = 0
    failures: list[str] = []

    try:
        async with sessionmaker() as session:
            ingestion = MarketDataIngestionService(
                provider,
                InstrumentRepository(session),
                CandleRepository(session),
            )
            for idx, symbol in enumerate(symbols, start=1):
                sym_fetched = 0
                sym_persisted = 0
                try:
                    for chunk_start, chunk_end in chunks:
                        f, p = await ingestion.ingest(
                            symbol,
                            "1m",
                            _as_utc_day(chunk_start),
                            _as_utc_day(chunk_end) + timedelta(hours=23, minutes=59),
                        )
                        sym_fetched += f
                        sym_persisted += p
                        if pause_s > 0:
                            await asyncio.sleep(pause_s)
                    await session.commit()
                    fetched_total += sym_fetched
                    persisted_total += sym_persisted
                    print(
                        f"[{idx}/{len(symbols)}] {symbol}: fetched={sym_fetched} persisted={sym_persisted}"
                    )
                except Exception as exc:  # noqa: BLE001 — continue universe
                    await session.rollback()
                    failures.append(f"{symbol}: {exc}")
                    print(f"[{idx}/{len(symbols)}] {symbol}: FAIL {exc}")
                    if pause_s > 0:
                        await asyncio.sleep(pause_s)
    finally:
        await factory.shutdown()
        await engine.dispose()

    print(
        f"Done universe={universe_name} range={start}→{end} "
        f"fetched={fetched_total} persisted={persisted_total} failures={len(failures)}"
    )
    if failures:
        print("Failures:")
        for row in failures[:20]:
            print(f"  {row}")


async def _ingest_today(*, universe_name: str, pause_s: float, limit_symbols: int | None) -> None:
    settings = get_settings()
    if normalize_market_data_source(settings.market_data_source) != "upstox":
        raise SystemExit("Set MARKET_DATA_SOURCE=upstox for today catch-up")

    universe = get_universe(universe_name)
    symbols = list(universe.get_snapshot().symbols)
    if limit_symbols is not None:
        symbols = symbols[: max(1, limit_symbols)]

    factory = UpstoxProviderFactory()
    provider = await factory.startup()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    persisted_total = 0
    failures: list[str] = []
    try:
        async with sessionmaker() as session:
            inst_repo = InstrumentRepository(session)
            candle_repo = CandleRepository(session)
            for idx, symbol in enumerate(symbols, start=1):
                try:
                    candles = await provider.get_intraday_candles(symbol, "1m")
                    if not candles:
                        print(f"[{idx}/{len(symbols)}] {symbol}: no intraday bars")
                        continue
                    inst = await inst_repo.get_or_create(symbol=symbol, exchange=candles[0].exchange)
                    rows = [
                        {
                            "instrument_id": inst.id,
                            "timestamp": c.timestamp,
                            "timeframe": "1m",
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in candles
                    ]
                    saved = await candle_repo.save_many(rows)
                    await session.commit()
                    persisted_total += saved
                    print(f"[{idx}/{len(symbols)}] {symbol}: today bars={len(rows)} persisted={saved}")
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    failures.append(f"{symbol}: {exc}")
                    print(f"[{idx}/{len(symbols)}] {symbol}: FAIL {exc}")
                if pause_s > 0:
                    await asyncio.sleep(pause_s)
    finally:
        await factory.shutdown()
        await engine.dispose()

    print(f"Today catch-up done persisted={persisted_total} failures={len(failures)}")


async def _ingest_demo_minutes(
    *,
    universe_name: str,
    start: date,
    end: date,
    limit_symbols: int | None,
) -> None:
    """Persist synthetic DemoMarketDataProvider minute bars (local persisted-path tests)."""
    from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider

    settings = get_settings()
    universe = get_universe(universe_name)
    symbols = list(universe.get_snapshot().symbols)
    # Include ORBDEMO for desk demos
    symbols = ["ORBDEMO", *symbols]
    if limit_symbols is not None:
        symbols = symbols[: max(1, limit_symbols)]

    provider = DemoMarketDataProvider()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    persisted_total = 0
    try:
        async with sessionmaker() as session:
            ingestion = MarketDataIngestionService(
                provider,
                InstrumentRepository(session),
                CandleRepository(session),
            )
            cur = start
            while cur <= end:
                if cur.weekday() < 5:
                    day_start = datetime(cur.year, cur.month, cur.day, 9, 15, tzinfo=IST)
                    day_end = datetime(cur.year, cur.month, cur.day, 15, 29, tzinfo=IST)
                    for symbol in symbols:
                        _f, p = await ingestion.ingest(symbol, "1m", day_start, day_end)
                        persisted_total += p
                    await session.commit()
                    print(f"demo 1m {cur}: symbols={len(symbols)} persisted_delta={persisted_total}")
                cur += timedelta(days=1)
    finally:
        await engine.dispose()
    print(f"Demo 1m seed done persisted={persisted_total}")


async def _ingest_watermark(
    *,
    universe_name: str,
    timeframe: str,
    pause_s: float,
    limit_symbols: int | None,
    lookback_days: int,
) -> None:
    """Incremental catch-up from each symbol's latest persisted bar (1m/5m/1d)."""
    settings = get_settings()
    if normalize_market_data_source(settings.market_data_source) != "upstox":
        raise SystemExit("Set MARKET_DATA_SOURCE=upstox for watermark catch-up")

    from app.application.market_data.watermark_ingestion_service import WatermarkIngestionService

    universe = get_universe(universe_name)
    symbols = list(universe.get_snapshot().symbols)
    if limit_symbols is not None:
        symbols = symbols[: max(1, limit_symbols)]

    factory = UpstoxProviderFactory()
    provider = await factory.startup()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    end = datetime.now(tz=timezone.utc)

    try:
        async with sessionmaker() as session:
            ingestion = MarketDataIngestionService(
                provider,
                InstrumentRepository(session),
                CandleRepository(session),
            )
            watermark = WatermarkIngestionService(
                ingestion,
                InstrumentRepository(session),
                CandleRepository(session),
                lookback_days=lookback_days,
            )
            # Process in small batches so one commit does not hold forever
            batch = 5
            for i in range(0, len(symbols), batch):
                chunk = symbols[i : i + batch]
                result = await watermark.ingest_symbols(chunk, timeframe, end)
                await session.commit()
                for row in result.results:
                    tag = "skip" if row.skipped else ("ok" if row.success else "FAIL")
                    detail = (
                        f"fetched={row.candles_fetched} persisted={row.candles_persisted}"
                        if row.success and not row.skipped
                        else (row.error_message or "")
                    )
                    print(f"[{tag}] {row.symbol}: {detail}")
                if pause_s > 0:
                    await asyncio.sleep(pause_s)
            print(
                f"Watermark done timeframe={timeframe} symbols={len(symbols)} end={end.isoformat()}"
            )
    finally:
        await factory.shutdown()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Upstox 1m candles")
    parser.add_argument("--universe", default="NIFTY_50")
    parser.add_argument(
        "--mode",
        choices=("range", "today", "demo", "watermark"),
        default="range",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--pause", type=float, default=0.15, help="Seconds between Upstox calls")
    parser.add_argument("--limit-symbols", type=int, default=None, help="Smoke: first N symbols")
    parser.add_argument(
        "--timeframe",
        default="1m",
        choices=("1m", "5m", "1d"),
        help="For --mode watermark",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=5,
        help="When no history exists (watermark mode)",
    )
    args = parser.parse_args()

    if args.mode == "today":
        _run_async(
            _ingest_today(
                universe_name=args.universe,
                pause_s=args.pause,
                limit_symbols=args.limit_symbols,
            )
        )
        return

    if args.mode == "watermark":
        _run_async(
            _ingest_watermark(
                universe_name=args.universe,
                timeframe=args.timeframe,
                pause_s=args.pause,
                limit_symbols=args.limit_symbols,
                lookback_days=args.lookback_days,
            )
        )
        return

    if args.mode == "demo":
        end = args.end or date(2026, 9, 7)
        # Need prior sessions for RVOL lookback when testing persisted path
        start = args.start or (end - timedelta(days=28))
        _run_async(
            _ingest_demo_minutes(
                universe_name=args.universe,
                start=start,
                end=end,
                limit_symbols=args.limit_symbols,
            )
        )
        return

    end = args.end or datetime.now(tz=IST).date()
    start = args.start or (end - timedelta(days=20))
    if start > end:
        raise SystemExit("--start must be <= --end")
    _run_async(
        _ingest_range(
            universe_name=args.universe,
            start=start,
            end=end,
            pause_s=args.pause,
            limit_symbols=args.limit_symbols,
        )
    )


if __name__ == "__main__":
    main()
