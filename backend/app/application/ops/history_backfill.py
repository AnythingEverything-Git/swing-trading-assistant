"""Long-running / staged 1m history backfill for RVOL lookback."""
from __future__ import annotations

import asyncio
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Sequence
from zoneinfo import ZoneInfo

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.universe import get_universe

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

ProgressCb = Callable[[dict[str, Any]], Awaitable[None] | None]

STAGE_NIFTY_50 = "NIFTY_50"
STAGE_NIFTY_100_REMAINING = "NIFTY_100_REMAINING"
STAGE_NIFTY_500_REMAINING = "NIFTY_500_REMAINING"
STAGE_NSE_ALL = "NSE_ALL"

KNOWN_STAGES = (
    STAGE_NIFTY_50,
    STAGE_NIFTY_100_REMAINING,
    STAGE_NIFTY_500_REMAINING,
    STAGE_NSE_ALL,
)


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


def default_history_window(*, lookback_days: int = 28) -> tuple[date, date]:
    end = datetime.now(tz=IST).date()
    start = end - timedelta(days=max(14, lookback_days))
    return start, end


def _symbols_for(name: str) -> list[str]:
    return list(get_universe(name).get_snapshot().symbols)


def resolve_stage_symbols(stage: str) -> list[str]:
    """Return ordered unique symbols for a backfill stage."""
    key = (stage or "").strip().upper()
    if key == STAGE_NIFTY_50:
        return _symbols_for("NIFTY_50")
    if key == STAGE_NIFTY_100_REMAINING:
        base = set(_symbols_for("NIFTY_50"))
        return [s for s in _symbols_for("NIFTY_100") if s not in base]
    if key == STAGE_NIFTY_500_REMAINING:
        base = set(_symbols_for("NIFTY_100"))
        return [s for s in _symbols_for("NIFTY_500") if s not in base]
    if key in ("NSE_ALL", "NIFTY_100", "NIFTY_200", "NIFTY_500", "NSE_CASH", "NSE_ETF"):
        return _symbols_for(key)
    # Treat unknown as universe name (legacy host_1m_history universe=NSE_ALL)
    return _symbols_for(key)


async def run_intraday_1m_history_backfill(
    app: Any | None = None,
    *,
    universe_name: str = "NSE_ALL",
    stage: str | None = None,
    symbols: Sequence[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    pause_s: float = 0.2,
    sessionmaker: Any | None = None,
    provider: Any | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Backfill historical 1m candles for RVOL (month-chunked Upstox pulls).

    Can run with FastAPI ``app`` state or standalone ``sessionmaker`` + ``provider``
    (ephemeral worker CLI).
    """
    resolved_end = end or datetime.now(tz=IST).date()
    resolved_start = start or (resolved_end - timedelta(days=28))
    if resolved_start > resolved_end:
        raise ValueError("start must be <= end")

    sm = sessionmaker
    prov = provider
    if app is not None:
        sm = sm or getattr(app.state, "sessionmaker", None)
        prov = prov or getattr(app.state, "ingest_provider", None)
    if sm is None or prov is None:
        raise RuntimeError("sessionmaker and ingest provider are required")

    label = (stage or universe_name or "NSE_ALL").strip().upper()
    if symbols is not None:
        resolved_symbols = [str(s).upper() for s in symbols]
    elif stage:
        resolved_symbols = resolve_stage_symbols(stage)
    else:
        resolved_symbols = resolve_stage_symbols(universe_name)

    chunks = _month_chunks(resolved_start, resolved_end)
    total = len(resolved_symbols)
    fetched_total = 0
    persisted_total = 0
    failures = 0

    async def _emit(payload: dict[str, Any]) -> None:
        if on_progress is None:
            return
        maybe = on_progress(payload)
        if asyncio.iscoroutine(maybe):
            await maybe

    await _emit(
        {
            "done": 0,
            "total": total,
            "current": None,
            "stage": label,
            "detail": (
                f"Starting stage={label} symbols={total} "
                f"{resolved_start}→{resolved_end} ({len(chunks)} month chunk(s))"
            ),
        }
    )
    logger.info(
        "1m history backfill start stage=%s symbols=%s range=%s→%s",
        label,
        total,
        resolved_start,
        resolved_end,
    )

    async with sm() as session:
        ingestion = MarketDataIngestionService(
            prov,
            InstrumentRepository(session),
            CandleRepository(session),
        )
        for idx, symbol in enumerate(resolved_symbols, start=1):
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
            except Exception:
                await session.rollback()
                failures += 1
                logger.exception("1m history backfill failed symbol=%s", symbol)
                if pause_s > 0:
                    await asyncio.sleep(pause_s)

            detail = (
                f"[{label}] {idx}/{total} {symbol}: fetched={sym_fetched} "
                f"persisted={sym_persisted} (cum_persisted={persisted_total} failures={failures})"
            )
            logger.info("%s", detail)
            await _emit(
                {
                    "done": idx,
                    "total": total,
                    "current": symbol,
                    "stage": label,
                    "detail": detail,
                }
            )

    summary = {
        "universe": label,
        "stage": label,
        "start": resolved_start.isoformat(),
        "end": resolved_end.isoformat(),
        "attempted": total,
        "persisted": persisted_total,
        "fetched": fetched_total,
        "failures": failures,
    }
    logger.info("1m history backfill finished %s", summary)
    return summary


__all__ = [
    "KNOWN_STAGES",
    "STAGE_NIFTY_50",
    "STAGE_NIFTY_100_REMAINING",
    "STAGE_NIFTY_500_REMAINING",
    "STAGE_NSE_ALL",
    "default_history_window",
    "resolve_stage_symbols",
    "run_intraday_1m_history_backfill",
]
