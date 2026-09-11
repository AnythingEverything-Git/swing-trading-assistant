"""In-app weekday IST schedule for watermark candle refresh.

Runs inside the FastAPI lifespan — no OS Task Scheduler. Calls the same
WatermarkIngestionService used by ``scripts/refresh_market_data.py``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.application.market_data.watermark_ingestion_service import WatermarkIngestionService
from app.application.ops.refresh_mutex import mark_refresh_mutex_held, release_refresh_mutex
from app.application.ops.scheduler_status import is_job_enabled, seed_registry_from_settings, touch_job
from app.core.config import Settings, get_settings
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.market_data.source import normalize_market_data_source
from app.infrastructure.universe import get_universe

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def parse_hhmm(value: str) -> tuple[int, int]:
    """Parse ``HH:MM`` (24h). Raises ValueError on bad input."""
    raw = (value or "").strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid HH:MM time: {value!r}")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid HH:MM time: {value!r}")
    return hour, minute


def next_weekday_fire(now_ist: datetime, hour: int, minute: int) -> datetime:
    """Next Mon–Fri fire at ``hour:minute`` Asia/Kolkata (exclusive of past today)."""
    if now_ist.tzinfo is None:
        now_ist = now_ist.replace(tzinfo=IST)
    else:
        now_ist = now_ist.astimezone(IST)

    candidate = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now_ist >= candidate:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:  # Saturday=5, Sunday=6
        candidate += timedelta(days=1)
    return candidate


def scheduler_should_run(settings: Settings | None = None) -> bool:
    """True when in-app watermark refresh is enabled for live Upstox."""
    cfg = settings or get_settings()
    if not bool(getattr(cfg, "market_data_refresh_enabled", True)):
        return False
    source = normalize_market_data_source(getattr(cfg, "market_data_source", "demo"))
    return source == "upstox"


def utc_today_end(*, now: datetime | None = None) -> datetime:
    """UTC midnight of today's UTC calendar date (same convention as demo seed end)."""
    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    return datetime(current.year, current.month, current.day, tzinfo=timezone.utc)


async def run_watermark_refresh(app: Any, *, end: datetime | None = None) -> dict[str, Any]:
    """Execute one watermark refresh using app.state sessionmaker + ingest provider."""
    settings = get_settings()
    universe_name = getattr(settings, "market_data_refresh_universe", "NIFTY_500") or "NIFTY_500"
    sessionmaker = getattr(app.state, "sessionmaker", None)
    provider = getattr(app.state, "ingest_provider", None)
    if sessionmaker is None or provider is None:
        raise RuntimeError("App state missing sessionmaker or ingest_provider")

    resolved_end = end or utc_today_end()
    universe = get_universe(universe_name)
    started = datetime.now(timezone.utc)
    logger.info(
        "Watermark refresh starting universe=%s end=%s",
        universe_name,
        resolved_end.date().isoformat(),
    )

    async with sessionmaker() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        ingestion = MarketDataIngestionService(provider, instrument_repo, candle_repo)
        watermark = WatermarkIngestionService(ingestion, instrument_repo, candle_repo)
        result = await watermark.ingest_universe(universe, "1d", resolved_end)
        await session.commit()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info(
        "Watermark refresh finished universe=%s attempted=%s success=%s skipped=%s "
        "failure=%s candles_persisted=%s elapsed_s=%.1f",
        universe_name,
        result.symbols_attempted,
        result.success_count,
        result.skipped_count,
        result.failure_count,
        result.candles_persisted,
        elapsed,
    )
    if result.failure_count:
        failed = [item for item in result.results if not item.success and not item.skipped]
        for item in failed[:20]:
            logger.warning(
                "Watermark refresh failed symbol=%s error=%s: %s",
                item.symbol,
                item.error_type,
                item.error_message,
            )
        if len(failed) > 20:
            logger.warning("Watermark refresh ... %s more failures", len(failed) - 20)

    return {
        "universe": universe_name,
        "attempted": result.symbols_attempted,
        "success": result.success_count,
        "skipped": result.skipped_count,
        "failure": result.failure_count,
        "candles_persisted": result.candles_persisted,
        "elapsed_s": round(elapsed, 1),
    }


async def run_intraday_1m_active_refresh(
    app: Any,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    """Watermark/catch-up 1m for a capped active universe during market hours."""
    settings = get_settings()
    if not force and not bool(getattr(settings, "intraday_1m_refresh_enabled", True)):
        return None
    sessionmaker = getattr(app.state, "sessionmaker", None)
    provider = getattr(app.state, "ingest_provider", None)
    if sessionmaker is None or provider is None:
        return None
    universe_name = getattr(settings, "intraday_1m_refresh_universe", "NIFTY_50") or "NIFTY_50"
    limit = int(getattr(settings, "intraday_1m_refresh_limit", 50) or 50)
    try:
        symbols = list(get_universe(universe_name).get_snapshot().symbols)[:limit]
    except ValueError:
        logger.warning("Intraday 1m refresh: unsupported universe %s", universe_name)
        return None

    from app.application.intraday.active_set_ingest import ensure_1m_for_symbols

    async with sessionmaker() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        result = await ensure_1m_for_symbols(
            symbols=symbols,
            provider=provider,
            instrument_repo=instrument_repo,
            candle_repo=candle_repo,
            pause_s=0.05,
        )
        await session.commit()
    logger.info(
        "Intraday 1m active refresh universe=%s attempted=%s saved=%s skipped=%s",
        universe_name,
        result.get("attempted"),
        result.get("saved"),
        result.get("skipped"),
    )
    return {
        "universe": universe_name,
        "attempted": result.get("attempted"),
        "saved": result.get("saved"),
        "skipped": result.get("skipped"),
    }


async def run_intraday_1m_today_refresh(
    app: Any,
    *,
    universe_name: str | None = None,
    pause_s: float = 0.05,
) -> dict[str, Any]:
    """Fetch today's Upstox intraday 1m bars for a universe (same as cron 1m today)."""
    settings = get_settings()
    resolved = universe_name or getattr(settings, "market_data_refresh_universe", "NSE_ALL") or "NSE_ALL"
    sessionmaker = getattr(app.state, "sessionmaker", None)
    provider = getattr(app.state, "ingest_provider", None)
    if sessionmaker is None or provider is None:
        raise RuntimeError("App state missing sessionmaker or ingest_provider")
    if not hasattr(provider, "get_intraday_candles"):
        raise RuntimeError("Ingest provider does not support intraday candles")

    symbols = list(get_universe(resolved).get_snapshot().symbols)
    attempted = 0
    persisted_total = 0
    failures = 0
    async with sessionmaker() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        for symbol in symbols:
            attempted += 1
            try:
                candles = await provider.get_intraday_candles(symbol, "1m")
                if not candles:
                    continue
                inst = await instrument_repo.get_or_create(symbol=symbol, exchange=candles[0].exchange)
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
            except Exception:
                await session.rollback()
                failures += 1
                logger.exception("1m today failed symbol=%s", symbol)
            if pause_s > 0:
                await asyncio.sleep(pause_s)
    logger.info(
        "Intraday 1m today refresh universe=%s attempted=%s persisted=%s failures=%s",
        resolved,
        attempted,
        persisted_total,
        failures,
    )
    return {
        "universe": resolved,
        "attempted": attempted,
        "persisted": persisted_total,
        "failures": failures,
    }


def _in_intraday_window(now_ist: datetime) -> bool:
    if now_ist.weekday() >= 5:
        return False
    minutes = now_ist.hour * 60 + now_ist.minute
    return (9 * 60 + 10) <= minutes <= (15 * 60 + 15)


def _detail_1d(summary: dict[str, Any]) -> str:
    return (
        f"attempted={summary.get('attempted')} success={summary.get('success')} "
        f"skipped={summary.get('skipped')} failure={summary.get('failure')} "
        f"candles={summary.get('candles_persisted')} ({summary.get('elapsed_s')}s)"
    )


def _detail_1m(summary: dict[str, Any]) -> str:
    return (
        f"attempted={summary.get('attempted')} saved={summary.get('saved')} "
        f"skipped={summary.get('skipped')}"
    )


async def refresh_scheduler_loop(app: Any, stop_event: asyncio.Event) -> None:
    """Weekday 1d watermark + optional intraday 1m active-set loop."""
    settings = get_settings()
    seed_registry_from_settings(app.state, settings)

    if not scheduler_should_run(settings):
        logger.info("Market-data refresh scheduler idle (disabled or non-upstox source)")
        await stop_event.wait()
        return

    try:
        hour, minute = parse_hhmm(getattr(settings, "market_data_refresh_time", "16:15"))
    except ValueError as exc:
        logger.error("Invalid MARKET_DATA_REFRESH_TIME: %s — scheduler stopped", exc)
        touch_job(
            app.state,
            "inapp_1d",
            status="failed",
            detail=f"Invalid MARKET_DATA_REFRESH_TIME: {exc}",
        )
        await stop_event.wait()
        return

    interval = max(60, int(getattr(settings, "intraday_1m_refresh_interval_sec", 300) or 300))

    if bool(getattr(settings, "market_data_refresh_run_on_startup", False)):
        if not getattr(app.state, "refresh_running", False):
            mark_refresh_mutex_held(app.state)
            touch_job(app.state, "inapp_1d", mark_started=True, phase="startup")
            try:
                summary = await run_watermark_refresh(app)
                touch_job(
                    app.state,
                    "inapp_1d",
                    mark_finished=True,
                    status="ok" if not summary.get("failure") else "ok",
                    detail=_detail_1d(summary),
                    phase=None,
                )
            except Exception as exc:
                logger.exception("Watermark refresh on startup failed")
                touch_job(
                    app.state,
                    "inapp_1d",
                    mark_finished=True,
                    status="failed",
                    detail=str(exc)[:240],
                    phase=None,
                )
            finally:
                release_refresh_mutex(app.state)

    next_1d = next_weekday_fire(datetime.now(IST), hour, minute)
    next_1m = datetime.now(IST)
    app.state.refresh_next_1d = next_1d
    app.state.refresh_next_1m = next_1m
    touch_job(app.state, "inapp_1d", next_run_at=next_1d.astimezone(timezone.utc))
    if bool(getattr(settings, "intraday_1m_refresh_enabled", True)):
        touch_job(app.state, "inapp_1m", next_run_at=next_1m.astimezone(timezone.utc))

    while not stop_event.is_set():
        now_ist = datetime.now(IST)
        one_m_on = is_job_enabled(app.state, "inapp_1m")
        one_d_on = is_job_enabled(app.state, "inapp_1d")

        # Intraday loop (Ops enable override can turn this on even if env default is off)
        if (
            one_m_on
            and _in_intraday_window(now_ist)
            and now_ist >= next_1m
            and not getattr(app.state, "refresh_running", False)
        ):
            mark_refresh_mutex_held(app.state)
            touch_job(app.state, "inapp_1m", mark_started=True)
            try:
                summary = await run_intraday_1m_active_refresh(app, force=True)
                detail = _detail_1m(summary) if summary else "skipped (no provider/universe)"
                touch_job(
                    app.state,
                    "inapp_1m",
                    mark_finished=True,
                    status="ok" if summary else "skipped",
                    detail=detail,
                )
            except Exception as exc:
                logger.exception("Intraday 1m refresh failed")
                touch_job(
                    app.state,
                    "inapp_1m",
                    mark_finished=True,
                    status="failed",
                    detail=str(exc)[:240],
                )
            finally:
                release_refresh_mutex(app.state)
            next_1m = now_ist + timedelta(seconds=interval)
            app.state.refresh_next_1m = next_1m
            touch_job(app.state, "inapp_1m", next_run_at=next_1m.astimezone(timezone.utc))

        # Daily 1d watermark
        if (
            one_d_on
            and now_ist >= next_1d
            and not getattr(app.state, "refresh_running", False)
        ):
            mark_refresh_mutex_held(app.state)
            touch_job(app.state, "inapp_1d", mark_started=True)
            try:
                summary = await run_watermark_refresh(app)
                touch_job(
                    app.state,
                    "inapp_1d",
                    mark_finished=True,
                    status="ok",
                    detail=_detail_1d(summary),
                )
            except Exception as exc:
                logger.exception("Scheduled watermark refresh failed")
                touch_job(
                    app.state,
                    "inapp_1d",
                    mark_finished=True,
                    status="failed",
                    detail=str(exc)[:240],
                )
            finally:
                release_refresh_mutex(app.state)
            next_1d = next_weekday_fire(datetime.now(IST), hour, minute)
            app.state.refresh_next_1d = next_1d
            touch_job(app.state, "inapp_1d", next_run_at=next_1d.astimezone(timezone.utc))

        # Keep next_run visible even while waiting outside the 1m window
        if one_m_on:
            app.state.refresh_next_1m = next_1m
            touch_job(app.state, "inapp_1m", next_run_at=next_1m.astimezone(timezone.utc))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            continue


__all__ = [
    "IST",
    "parse_hhmm",
    "next_weekday_fire",
    "scheduler_should_run",
    "utc_today_end",
    "run_watermark_refresh",
    "run_intraday_1m_active_refresh",
    "run_intraday_1m_today_refresh",
    "refresh_scheduler_loop",
]
