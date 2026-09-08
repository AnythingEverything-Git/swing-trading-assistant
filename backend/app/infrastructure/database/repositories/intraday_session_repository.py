"""Persistence for intraday ORB session runs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.intraday_session import IntradaySessionORM


class IntradaySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(
        self,
        *,
        session_id: str,
        created_at: datetime,
        session_date: date,
        strategy_id: str,
        config_hash: str,
        data_source: str,
        equity: Decimal | None,
        coverage_eligible: int,
        coverage_total: int,
        fill_count: int,
        realized_pnl: Decimal | None,
        result_payload: dict[str, Any],
        meta: dict[str, Any] | None,
    ) -> IntradaySessionORM:
        row = IntradaySessionORM(
            id=session_id,
            created_at=created_at,
            session_date=session_date,
            strategy_id=strategy_id,
            config_hash=config_hash,
            data_source=data_source,
            equity=equity,
            coverage_eligible=coverage_eligible,
            coverage_total=coverage_total,
            fill_count=fill_count,
            realized_pnl=realized_pnl,
            result_payload=result_payload,
            meta=meta,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, session_id: str) -> IntradaySessionORM | None:
        result = await self.session.execute(
            select(IntradaySessionORM).where(IntradaySessionORM.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, *, limit: int = 20) -> list[IntradaySessionORM]:
        result = await self.session.execute(
            select(IntradaySessionORM)
            .order_by(desc(IntradaySessionORM.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
