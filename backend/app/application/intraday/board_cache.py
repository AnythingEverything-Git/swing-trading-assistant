"""Morning-board cache + background rebuild (accuracy-identical payloads, ≤3s HTTP)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Fresh enough to serve without kicking a rebuild (seconds).
_DEFAULT_TTL_SEC = 25.0
# Absolute max age for stale-while-revalidate (still accurate prior snapshot).
_STALE_MAX_SEC = 300.0


def board_cache_key(
    *,
    universe: str,
    session_date: date | None,
    source: str,
    filters: dict | None,
    symbols: list[str] | None,
    equity: Decimal | None = None,
) -> str:
    payload = {
        "universe": (universe or "NIFTY_500").strip().upper(),
        "session_date": session_date.isoformat() if session_date else None,
        "source": source,
        "filters": filters or {},
        "symbols": sorted(s.upper() for s in (symbols or [])),
        "equity": str(equity) if equity is not None else None,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_store(app: FastAPI) -> dict[str, dict[str, Any]]:
    store = getattr(app.state, "morning_board_cache", None)
    if not isinstance(store, dict):
        store = {}
        app.state.morning_board_cache = store
    return store


def _jobs(app: FastAPI) -> dict[str, dict[str, Any]]:
    jobs = getattr(app.state, "morning_board_jobs", None)
    if not isinstance(jobs, dict):
        jobs = {}
        app.state.morning_board_jobs = jobs
    return jobs


def get_cached_board(app: FastAPI, key: str) -> dict[str, Any] | None:
    entry = _cache_store(app).get(key)
    if not entry:
        return None
    age = time.monotonic() - float(entry.get("saved_mono") or 0)
    if age > _STALE_MAX_SEC:
        return None
    board = dict(entry.get("board") or {})
    board["cache"] = {
        "hit": True,
        "age_sec": round(age, 2),
        "stale": age > _DEFAULT_TTL_SEC,
        "as_of": entry.get("as_of"),
    }
    return board


def put_cached_board(app: FastAPI, key: str, board: dict[str, Any]) -> None:
    _cache_store(app)[key] = {
        "board": board,
        "saved_mono": time.monotonic(),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def job_status(app: FastAPI, job_id: str) -> dict[str, Any] | None:
    job = _jobs(app).get(job_id)
    if not job:
        return None
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "cache_key": job.get("cache_key"),
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


async def build_and_cache_board(
    app: FastAPI,
    *,
    cache_key: str,
    session_date: date | None,
    source: str,
    equity: Decimal,
    filters: dict | None,
    universe: str,
    symbols: list[str] | None,
) -> dict[str, Any]:
    from app.application.intraday.morning_board_service import build_morning_board
    from app.application.market_data.query_service import MarketDataQueryService
    from app.infrastructure.database.repositories.candle_repository import CandleRepository
    from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository

    sessionmaker = getattr(app.state, "sessionmaker", None)
    if sessionmaker is None:
        raise RuntimeError("Database not configured")

    async with sessionmaker() as session:
        query = None
        if source == "persisted":
            query = MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
        board = await build_morning_board(
            session_date=session_date,
            source=source,  # type: ignore[arg-type]
            query=query,
            equity=equity,
            filters=filters,
            universe=universe,
            symbols=symbols,
        )
        await session.commit()
    put_cached_board(app, cache_key, board)
    return board


def start_board_rebuild(
    app: FastAPI,
    *,
    cache_key: str,
    session_date: date | None,
    source: str,
    equity: Decimal,
    filters: dict | None,
    universe: str,
    symbols: list[str] | None,
) -> str:
    """Enqueue a background rebuild if one is not already running for this key."""
    jobs = _jobs(app)
    for jid, job in list(jobs.items()):
        if job.get("cache_key") == cache_key and job.get("status") in ("queued", "running"):
            return jid

    job_id = f"mb-{cache_key[:12]}-{int(time.time())}"
    jobs[job_id] = {
        "status": "queued",
        "cache_key": cache_key,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
    }

    async def _run() -> None:
        # Yield so the accepting HTTP response can flush before heavy DB work.
        await asyncio.sleep(0)
        jobs[job_id]["status"] = "running"
        try:
            await build_and_cache_board(
                app,
                cache_key=cache_key,
                session_date=session_date,
                source=source,
                equity=equity,
                filters=filters,
                universe=universe,
                symbols=symbols,
            )
            jobs[job_id]["status"] = "ready"
        except Exception as exc:
            logger.exception("morning board rebuild failed")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)[:400]
        finally:
            jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()

    task = asyncio.create_task(_run(), name=f"morning-board-{job_id}")
    running = getattr(app.state, "morning_board_tasks", None)
    if not isinstance(running, list):
        running = []
        app.state.morning_board_tasks = running
    running.append(task)

    def _cleanup(done: asyncio.Task) -> None:
        try:
            running.remove(done)
        except ValueError:
            pass

    task.add_done_callback(_cleanup)
    return job_id


async def serve_morning_board(
    app: FastAPI,
    *,
    session_date: date | None,
    source: str,
    equity: Decimal,
    filters: dict | None,
    universe: str,
    symbols: list[str] | None,
    force_refresh: bool = False,
) -> tuple[dict[str, Any], int]:
    """Return (body, http_status). Prefer cache ≤3s; kick rebuild when stale/missing."""
    uni = (universe or "NIFTY_500").strip().upper() or "NIFTY_500"
    key = board_cache_key(
        universe=uni,
        session_date=session_date,
        source=source,
        filters=filters,
        symbols=symbols,
        equity=equity,
    )
    cached = None if force_refresh else get_cached_board(app, key)
    if cached is not None:
        age = float((cached.get("cache") or {}).get("age_sec") or 0)
        if age > _DEFAULT_TTL_SEC or force_refresh:
            job_id = start_board_rebuild(
                app,
                cache_key=key,
                session_date=session_date,
                source=source,
                equity=equity,
                filters=filters,
                universe=uni,
                symbols=symbols,
            )
            cached["rebuild_job_id"] = job_id
        return cached, 200

    # No cache: accept immediately (202). Full accurate ranks land via poll/SWR —
    # never hold the HTTP request on the Free Tier event loop for a first paint wait.
    job_id = start_board_rebuild(
        app,
        cache_key=key,
        session_date=session_date,
        source=source,
        equity=equity,
        filters=filters,
        universe=uni,
        symbols=symbols,
    )
    return {
        "status": "running",
        "job_id": job_id,
        "message": "Morning board building — poll job or retry shortly for full accurate ranks.",
        "universe": uni,
        "session_date": session_date.isoformat() if session_date else None,
    }, 202


__all__ = [
    "board_cache_key",
    "get_cached_board",
    "serve_morning_board",
    "job_status",
    "start_board_rebuild",
]
