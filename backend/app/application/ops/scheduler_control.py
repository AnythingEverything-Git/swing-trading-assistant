"""Manual start / control helpers for ops scheduler dashboard."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from app.application.market_data.refresh_scheduler import (
    run_intraday_1m_active_refresh,
    run_intraday_1m_today_refresh,
    run_watermark_refresh,
)
from app.application.ops.history_backfill import (
    default_history_window,
    run_intraday_1m_history_backfill,
)
from app.application.ops.refresh_mutex import mark_refresh_mutex_held, release_refresh_mutex
from app.application.ops.scheduler_status import (
    RUNNABLE_JOB_IDS,
    is_job_enabled,
    touch_job,
)

logger = logging.getLogger(__name__)

HISTORY_JOB_ID = "host_1m_history"


def _detail_1d(summary: dict[str, Any]) -> str:
    return (
        f"attempted={summary.get('attempted')} success={summary.get('success')} "
        f"skipped={summary.get('skipped')} failure={summary.get('failure')} "
        f"candles={summary.get('candles_persisted')} ({summary.get('elapsed_s')}s)"
    )


def _detail_1m(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "skipped (no provider/universe)"
    if "saved" in summary:
        return (
            f"attempted={summary.get('attempted')} saved={summary.get('saved')} "
            f"skipped={summary.get('skipped')}"
        )
    return (
        f"attempted={summary.get('attempted')} persisted={summary.get('persisted')} "
        f"failures={summary.get('failures')}"
    )


async def _progress_history(app: Any, payload: dict[str, Any]) -> None:
    touch_job(
        app.state,
        HISTORY_JOB_ID,
        running=True,
        status="running",
        detail=str(payload.get("detail") or "")[:320],
        phase="history_backfill",
        progress_done=int(payload.get("done") or 0),
        progress_total=int(payload.get("total") or 0) or None,
        progress_current=payload.get("current"),
    )


async def _run_history_body(
    app: Any,
    *,
    stage: str,
    start: date,
    end: date,
) -> None:
    touch_job(
        app.state,
        HISTORY_JOB_ID,
        mark_started=True,
        phase=stage,
        detail=f"Queued {stage} {start}→{end}",
        progress_done=0,
        progress_total=None,
        progress_current=None,
    )
    try:
        summary = await run_intraday_1m_history_backfill(
            app,
            stage=stage,
            start=start,
            end=end,
            on_progress=lambda p: _progress_history(app, p),
        )
        touch_job(
            app.state,
            HISTORY_JOB_ID,
            mark_finished=True,
            status="ok",
            detail=(
                f"done {summary.get('stage')} {summary.get('start')}→{summary.get('end')} "
                f"persisted={summary.get('persisted')} failures={summary.get('failures')}"
            ),
            phase=None,
            progress_done=int(summary.get("attempted") or 0),
            progress_total=int(summary.get("attempted") or 0),
            progress_current=None,
        )
    except Exception as exc:
        logger.exception("1m history backfill failed")
        touch_job(
            app.state,
            HISTORY_JOB_ID,
            mark_finished=True,
            status="failed",
            detail=str(exc)[:240],
            phase=None,
        )
    finally:
        app.state.history_backfill_running = False


async def _run_job_body(app: Any, job_id: str) -> None:
    touch_job(app.state, job_id, mark_started=True, phase="manual")
    try:
        if job_id in ("inapp_1d", "cron_1d"):
            summary = await run_watermark_refresh(app)
            touch_job(
                app.state,
                job_id,
                mark_finished=True,
                status="ok",
                detail=_detail_1d(summary),
                phase=None,
            )
        elif job_id == "inapp_1m":
            summary = await run_intraday_1m_active_refresh(app, force=True)
            touch_job(
                app.state,
                job_id,
                mark_finished=True,
                status="ok" if summary else "skipped",
                detail=_detail_1m(summary),
                phase=None,
            )
        elif job_id == "cron_1m_today":
            summary = await run_intraday_1m_today_refresh(app)
            touch_job(
                app.state,
                job_id,
                mark_finished=True,
                status="ok",
                detail=_detail_1m(summary),
                phase=None,
            )
        else:
            touch_job(
                app.state,
                job_id,
                mark_finished=True,
                status="failed",
                detail=f"Manual run not supported for {job_id}",
                phase=None,
            )
    except Exception as exc:
        logger.exception("Manual scheduler run failed job_id=%s", job_id)
        touch_job(
            app.state,
            job_id,
            mark_finished=True,
            status="failed",
            detail=str(exc)[:240],
            phase=None,
        )
    finally:
        release_refresh_mutex(app.state)
    running = getattr(app.state, "ops_manual_tasks", None)
    if not isinstance(running, list):
        running = []
        app.state.ops_manual_tasks = running
    running.append(task)

    def _cleanup(done: asyncio.Task) -> None:
        try:
            running.remove(done)
        except ValueError:
            pass

    task.add_done_callback(_cleanup)


def start_job_manual(
    app: Any,
    job_id: str,
    *,
    universe: str | None = None,
    stage: str | None = None,
    start: date | None = None,
    end: date | None = None,
    lookback_days: int = 28,
) -> dict[str, Any]:
    """Validate and kick off a background manual run. Returns acceptance payload."""
    if job_id not in RUNNABLE_JOB_IDS:
        raise ValueError(
            f"Manual run not supported for {job_id} "
            "(use host script for universe rebuild / perfect-today)"
        )
    if not is_job_enabled(app.state, job_id):
        raise PermissionError(f"Job {job_id} is disabled — enable it first")

    if job_id == HISTORY_JOB_ID:
        if getattr(app.state, "history_backfill_running", False):
            raise RuntimeError("1m history backfill is already running")
        win_start, win_end = default_history_window(lookback_days=lookback_days)
        resolved_start = start or win_start
        resolved_end = end or win_end
        resolved_stage = (stage or universe or "NIFTY_50").strip().upper() or "NIFTY_50"
        app.state.history_backfill_running = True
        touch_job(
            app.state,
            HISTORY_JOB_ID,
            mark_started=True,
            phase=resolved_stage,
            detail=f"Queued {resolved_stage} {resolved_start}→{resolved_end}",
            progress_done=0,
            progress_total=None,
        )
        task = asyncio.create_task(
            _run_history_body(
                app,
                stage=resolved_stage,
                start=resolved_start,
                end=resolved_end,
            ),
            name="ops-manual-host_1m_history",
        )
        _track_task(app, task)
        return {
            "accepted": True,
            "job_id": job_id,
            "status": "running",
            "universe": resolved_stage,
            "start": resolved_start.isoformat(),
            "end": resolved_end.isoformat(),
        }

    if getattr(app.state, "refresh_running", False):
        raise RuntimeError("Another refresh job is already running (mutex held)")

    mark_refresh_mutex_held(app.state)
    touch_job(app.state, job_id, mark_started=True, phase="manual", detail="Queued manual run")
    task = asyncio.create_task(_run_job_body(app, job_id), name=f"ops-manual-{job_id}")
    _track_task(app, task)
    return {"accepted": True, "job_id": job_id, "status": "running"}


__all__ = ["HISTORY_JOB_ID", "start_job_manual"]
