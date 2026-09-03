"""Persistence for ScanRun audit records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.scan_run import ScanRun
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
        )
