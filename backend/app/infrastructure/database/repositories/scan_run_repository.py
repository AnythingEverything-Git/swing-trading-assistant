"""Persistence for ScanRun audit records."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.scan_run import (
    SCAN_STATUS_COMPLETED,
    SCAN_STATUS_FAILED,
    SCAN_STATUS_QUEUED,
    SCAN_STATUS_RUNNING,
    ScanRun,
)
from app.infrastructure.database.models import ScanRunORM


class ScanRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        started_at: datetime,
        finished_at: datetime | None = None,
        universe_date: datetime | None = None,
        universe_version: str | None = None,
        parameters: dict[str, Any] | None = None,
        result_count: int = 0,
        metadata: dict[str, Any] | None = None,
        result_payload: dict[str, Any] | None = None,
        status: str = SCAN_STATUS_COMPLETED,
        error_message: str | None = None,
    ) -> ScanRun:
        row = ScanRunORM(
            started_at=started_at,
            finished_at=finished_at,
            universe_date=universe_date,
            universe_version=universe_version,
            parameters=parameters,
            result_count=result_count,
            metadata_=metadata,
            result_payload=result_payload,
            status=status,
            error_message=error_message,
        )
        self.session.add(row)
        await self.session.flush()
        return self._to_domain(row)

    async def get_by_id(self, scan_run_id: int) -> ScanRun | None:
        row = await self.session.get(ScanRunORM, scan_run_id)
        if row is None:
            return None
        return self._to_domain(row)

    async def list_recent(self, limit: int = 20) -> list[ScanRun]:
        stmt = select(ScanRunORM).order_by(desc(ScanRunORM.id)).limit(max(1, min(limit, 100)))
        result = await self.session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def list_ids_by_status(self, statuses: list[str], *, limit: int = 50) -> list[int]:
        stmt = (
            select(ScanRunORM.id)
            .where(ScanRunORM.status.in_(statuses))
            .order_by(ScanRunORM.id.asc())
            .limit(max(1, min(limit, 200)))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_running(self, scan_run_id: int) -> None:
        await self.session.execute(
            update(ScanRunORM)
            .where(ScanRunORM.id == scan_run_id)
            .values(status=SCAN_STATUS_RUNNING, error_message=None)
        )

    async def mark_completed(
        self,
        scan_run_id: int,
        *,
        finished_at: datetime,
        result_count: int,
        metadata: dict[str, Any] | None,
        result_payload: dict[str, Any],
    ) -> None:
        await self.session.execute(
            update(ScanRunORM)
            .where(ScanRunORM.id == scan_run_id)
            .values(
                status=SCAN_STATUS_COMPLETED,
                finished_at=finished_at,
                result_count=result_count,
                metadata_=metadata,
                result_payload=result_payload,
                error_message=None,
            )
        )

    async def mark_failed(
        self,
        scan_run_id: int,
        *,
        finished_at: datetime,
        error_message: str,
    ) -> None:
        await self.session.execute(
            update(ScanRunORM)
            .where(ScanRunORM.id == scan_run_id)
            .values(
                status=SCAN_STATUS_FAILED,
                finished_at=finished_at,
                error_message=error_message[:2000],
            )
        )

    async def reclaim_stale_jobs(self) -> list[int]:
        """Re-queue interrupted jobs after process restart; fail stuck running once."""
        queued = await self.list_ids_by_status([SCAN_STATUS_QUEUED])
        running = await self.list_ids_by_status([SCAN_STATUS_RUNNING])
        now = datetime.now(timezone.utc)
        for scan_run_id in running:
            await self.mark_failed(
                scan_run_id,
                finished_at=now,
                error_message="Scan interrupted by server restart",
            )
        return queued

    @staticmethod
    def _to_domain(row: ScanRunORM) -> ScanRun:
        return ScanRun(
            id=row.id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            universe_date=row.universe_date,
            universe_version=row.universe_version,
            parameters=row.parameters,
            result_count=row.result_count,
            metadata=row.metadata_,
            result_payload=row.result_payload,
            status=getattr(row, "status", None) or SCAN_STATUS_COMPLETED,
            error_message=getattr(row, "error_message", None),
        )
