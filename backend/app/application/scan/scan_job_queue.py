"""In-process asyncio queue for scan jobs (no Redis)."""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository

logger = logging.getLogger(__name__)


class ScanJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def enqueue(self, scan_run_id: int) -> None:
        self._queue.put_nowait(scan_run_id)

    def ensure_worker(self, app: FastAPI) -> None:
        """Restart the worker if reload/crash left queued jobs unconsumed."""
        if self._task is not None and not self._task.done() and not self._stop.is_set():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._worker_loop(app), name="scan-job-worker")
        logger.warning("Scan job worker was not running; restarted")

    async def start(self, app: FastAPI) -> None:
        self._stop.clear()
        await self._reclaim(app)
        self._task = asyncio.create_task(self._worker_loop(app), name="scan-job-worker")
        logger.info("Scan job worker started")

    async def stop(self) -> None:
        self._stop.set()
        # Unblock waiter
        try:
            self._queue.put_nowait(-1)
        except Exception:
            pass
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                logger.exception("Error while stopping scan job worker")
            self._task = None

    async def _reclaim(self, app: FastAPI) -> None:
        sessionmaker = getattr(app.state, "sessionmaker", None)
        if sessionmaker is None:
            return
        try:
            async with sessionmaker() as session:
                repo = ScanRunRepository(session)
                queued_ids = await repo.reclaim_stale_jobs()
                await session.commit()
            for scan_run_id in queued_ids:
                self.enqueue(scan_run_id)
            if queued_ids:
                logger.info("Re-queued %s interrupted scan jobs", len(queued_ids))
        except Exception:
            logger.exception("Failed to reclaim stale scan jobs")

    async def _worker_loop(self, app: FastAPI) -> None:
        from app.application.scan.scan_job_service import execute_scan_job_for_app

        while not self._stop.is_set():
            try:
                scan_run_id = await self._queue.get()
            except asyncio.CancelledError:
                break
            if scan_run_id < 0 or self._stop.is_set():
                break
            try:
                await execute_scan_job_for_app(app, scan_run_id)
            except Exception:
                logger.exception("Unhandled error in scan worker for id=%s", scan_run_id)


def get_or_create_scan_queue(app: FastAPI) -> ScanJobQueue:
    queue = getattr(app.state, "scan_job_queue", None)
    if queue is None:
        queue = ScanJobQueue()
        app.state.scan_job_queue = queue
    return queue
