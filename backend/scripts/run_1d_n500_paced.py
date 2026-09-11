"""Paced 1d watermark retry for NIFTY_500 symbols behind provider_max.

Finds symbols whose max 1d timestamp is below the universe provider max (or an
optional --min-ts), then watermark-ingests them one-by-one with sleep + exponential
backoff on HTTP 429 / rate-limit errors.

Usage (from backend/, inside api container):

    python scripts/run_1d_n500_paced.py
    python scripts/run_1d_n500_paced.py --universe NIFTY_500 --sleep 1.5 --max-retries 5
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import func, select

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.application.market_data.refresh_scheduler import utc_today_end
from app.application.market_data.watermark_ingestion_service import WatermarkIngestionService
from app.core.config import get_settings
from app.infrastructure.database.models.candle import CandleORM
from app.infrastructure.database.models.instrument import InstrumentORM
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.session import create_engine, create_sessionmaker
from app.infrastructure.market_data.factory import UpstoxProviderFactory
from app.infrastructure.market_data.source import normalize_market_data_source
from app.infrastructure.universe import get_universe


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def _is_rate_limited(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "429" in text or "rate" in text or "too many" in text


async def _max_1d_by_symbol(session, symbols: list[str]) -> dict[str, datetime]:
    if not symbols:
        return {}
    stmt = (
        select(InstrumentORM.symbol, func.max(CandleORM.timestamp))
        .join(CandleORM, CandleORM.instrument_id == InstrumentORM.id)
        .where(InstrumentORM.symbol.in_(symbols))
        .where(CandleORM.timeframe == "1d")
        .group_by(InstrumentORM.symbol)
    )
    result = await session.execute(stmt)
    out: dict[str, datetime] = {}
    for sym, ts in result.fetchall():
        if sym and ts is not None:
            out[str(sym).strip().upper()] = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return out


async def run_paced(
    *,
    universe_name: str,
    sleep_s: float,
    max_retries: int,
    backoff_base: float,
) -> int:
    settings = get_settings()
    source = normalize_market_data_source(settings.market_data_source)
    if source != "upstox":
        raise SystemExit("Refusing paced 1d: MARKET_DATA_SOURCE must be upstox")

    snap = get_universe(universe_name).get_snapshot()
    symbols = [str(s).strip().upper() for s in snap.symbols]
    end = utc_today_end()

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    factory = UpstoxProviderFactory()
    provider = await factory.startup()
    exit_code = 0
    try:
        async with sessionmaker() as session:
            max_1d = await _max_1d_by_symbol(session, symbols)
            provider_max = max(max_1d.values()) if max_1d else None
            if provider_max is None:
                print("No 1d candles found for universe — nothing to pace")
                return 1

            behind = sorted(
                s
                for s in symbols
                if s not in max_1d or max_1d[s] < provider_max
            )
            print(
                f"universe={universe_name} symbols={len(symbols)} "
                f"provider_1d_max={provider_max.isoformat()} behind={len(behind)}"
            )
            if not behind:
                print("All symbols already at provider_1d_max")
                return 0

            instrument_repo = InstrumentRepository(session)
            candle_repo = CandleRepository(session)
            ingestion = MarketDataIngestionService(provider, instrument_repo, candle_repo)
            watermark = WatermarkIngestionService(ingestion, instrument_repo, candle_repo)

            success = 0
            failed = 0
            for idx, symbol in enumerate(behind, start=1):
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        result = await watermark.ingest_symbols([symbol], "1d", end)
                        await session.commit()
                        item = result.results[0] if result.results else None
                        if item and not item.success and not item.skipped:
                            raise RuntimeError(
                                f"{item.error_type}: {item.error_message}"
                            )
                        success += 1
                        detail = "skipped" if item and item.skipped else f"persisted={item.candles_persisted if item else 0}"
                        print(f"[{idx}/{len(behind)}] {symbol} ok ({detail})")
                        break
                    except Exception as exc:
                        if _is_rate_limited(exc) and attempt <= max_retries:
                            delay = backoff_base * (2 ** (attempt - 1))
                            print(
                                f"[{idx}/{len(behind)}] {symbol} 429/backoff "
                                f"attempt={attempt} sleep={delay:.1f}s ({exc})"
                            )
                            await session.rollback()
                            await asyncio.sleep(delay)
                            continue
                        failed += 1
                        exit_code = 1
                        print(f"[{idx}/{len(behind)}] {symbol} FAIL: {exc}")
                        await session.rollback()
                        break

                if sleep_s > 0 and idx < len(behind):
                    await asyncio.sleep(sleep_s)

            print(f"DONE success={success} failed={failed} behind_was={len(behind)}")
            return exit_code
    finally:
        await factory.shutdown()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Paced 1d retry for symbols behind provider_max")
    parser.add_argument("--universe", default="NIFTY_500")
    parser.add_argument("--sleep", type=float, default=1.25, help="Seconds between symbols")
    parser.add_argument("--max-retries", type=int, default=6)
    parser.add_argument("--backoff-base", type=float, default=2.0)
    args = parser.parse_args()
    code = _run_async(
        run_paced(
            universe_name=args.universe.strip().upper(),
            sleep_s=max(0.0, args.sleep),
            max_retries=max(1, args.max_retries),
            backoff_base=max(0.5, args.backoff_base),
        )
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
