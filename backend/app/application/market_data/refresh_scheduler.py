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


async def run_watermark_refresh(app: Any, *, end: datetime | None = None) -> None:
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


async def refresh_scheduler_loop(app: Any, stop_event: asyncio.Event) -> None:
    """Wait until each weekday IST fire time and run watermark refresh."""
    settings = get_settings()
    if not scheduler_should_run(settings):
        logger.info("Market-data refresh scheduler idle (disabled or non-upstox source)")
        await stop_event.wait()
        return

    try:
        hour, minute = parse_hhmm(getattr(settings, "market_data_refresh_time", "16:15"))
    except ValueError as exc:
        logger.error("Invalid MARKET_DATA_REFRESH_TIME: %s — scheduler stopped", exc)
        await stop_event.wait()
        return

    if bool(getattr(settings, "market_data_refresh_run_on_startup", False)):
        if not getattr(app.state, "refresh_running", False):
            app.state.refresh_running = True
            try:
                await run_watermark_refresh(app)
            except Exception:
                logger.exception("Watermark refresh on startup failed")
            finally:
                app.state.refresh_running = False

    while not stop_event.is_set():
        now_ist = datetime.now(IST)
        next_fire = next_weekday_fire(now_ist, hour, minute)
        delay = max(1.0, (next_fire - now_ist).total_seconds())
        logger.info(
            "Market-data refresh scheduled next_fire_ist=%s delay_s=%.0f",
            next_fire.isoformat(),
            delay,
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            break
        except asyncio.TimeoutError:
            pass

        if stop_event.is_set():
            break

        if getattr(app.state, "refresh_running", False):
            logger.warning("Skipping watermark refresh — previous run still in progress")
            continue

        app.state.refresh_running = True
        try:
            await run_watermark_refresh(app)
        except Exception:
            logger.exception("Scheduled watermark refresh failed")
        finally:
            app.state.refresh_running = False


__all__ = [
    "IST",
    "parse_hhmm",
    "next_weekday_fire",
    "scheduler_should_run",
    "utc_today_end",
    "run_watermark_refresh",
    "refresh_scheduler_loop",
]
