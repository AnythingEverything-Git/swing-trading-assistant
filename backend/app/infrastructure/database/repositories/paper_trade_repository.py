"""Persistence for simulated paper trades."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.paper import PaperTrade
from app.infrastructure.database.models import PaperTradeORM


class PaperTradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, trade: PaperTrade) -> PaperTrade:
        row = self._to_orm(trade)
        self.session.add(row)
        await self.session.flush()
        return self._to_domain(row)

    async def save(self, trade: PaperTrade) -> PaperTrade:
        if trade.id is None:
            return await self.create(trade)
        row = await self.session.get(PaperTradeORM, trade.id)
        if row is None:
            raise ValueError(f"paper trade {trade.id} not found")
        self._apply(row, trade)
        await self.session.flush()
        return self._to_domain(row)

    async def get_by_id(self, trade_id: int) -> PaperTrade | None:
        row = await self.session.get(PaperTradeORM, trade_id)
        return None if row is None else self._to_domain(row)

    async def list_active_symbols(self) -> set[str]:
        stmt = select(PaperTradeORM.symbol).where(PaperTradeORM.status.in_(("PENDING", "OPEN")))
        result = await self.session.execute(stmt)
        return {row for row in result.scalars().all()}

    async def list_open_symbols(self) -> set[str]:
        return await self.list_active_symbols()

    async def list_by_status(self, status: str | None = None, *, limit: int = 200) -> list[PaperTrade]:
        stmt = select(PaperTradeORM).order_by(PaperTradeORM.id.desc()).limit(max(1, min(limit, 500)))
        if status and status != "ALL":
            if status == "ACTIVE":
                stmt = stmt.where(PaperTradeORM.status.in_(("PENDING", "OPEN")))
            else:
                stmt = stmt.where(PaperTradeORM.status == status)
        result = await self.session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def list_open(self) -> list[PaperTrade]:
        return await self.list_by_status("OPEN", limit=500)

    async def list_active(self) -> list[PaperTrade]:
        return await self.list_by_status("ACTIVE", limit=500)

    @staticmethod
    def _to_orm(trade: PaperTrade) -> PaperTradeORM:
        return PaperTradeORM(
            scan_run_id=trade.scan_run_id,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            target=trade.target,
            quantity=trade.quantity,
            risk_amount=trade.risk_amount,
            status=trade.status,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            exit_price=trade.exit_price,
            exit_reason=trade.exit_reason,
            last_mark_price=trade.last_mark_price,
            unrealized_pnl=trade.unrealized_pnl,
            realized_pnl=trade.realized_pnl,
            setup_name=trade.setup_name,
            quality_score=trade.quality_score,
            updated_at=trade.updated_at,
        )

    @staticmethod
    def _apply(row: PaperTradeORM, trade: PaperTrade) -> None:
        row.scan_run_id = trade.scan_run_id
        row.symbol = trade.symbol
        row.direction = trade.direction
        row.entry_price = trade.entry_price
        row.stop_loss = trade.stop_loss
        row.target = trade.target
        row.quantity = trade.quantity
        row.risk_amount = trade.risk_amount
        row.status = trade.status
        row.opened_at = trade.opened_at
        row.closed_at = trade.closed_at
        row.exit_price = trade.exit_price
        row.exit_reason = trade.exit_reason
        row.last_mark_price = trade.last_mark_price
        row.unrealized_pnl = trade.unrealized_pnl
        row.realized_pnl = trade.realized_pnl
        row.setup_name = trade.setup_name
        row.quality_score = trade.quality_score
        row.updated_at = trade.updated_at

    @staticmethod
    def _to_domain(row: PaperTradeORM) -> PaperTrade:
        return PaperTrade(
            id=row.id,
            scan_run_id=row.scan_run_id,
            symbol=row.symbol,
            direction=row.direction,  # type: ignore[arg-type]
            entry_price=Decimal(str(row.entry_price)),
            stop_loss=Decimal(str(row.stop_loss)),
            target=Decimal(str(row.target)),
            quantity=row.quantity,
            risk_amount=None if row.risk_amount is None else Decimal(str(row.risk_amount)),
            status=row.status,  # type: ignore[arg-type]
            opened_at=row.opened_at,
            closed_at=row.closed_at,
            exit_price=None if row.exit_price is None else Decimal(str(row.exit_price)),
            exit_reason=row.exit_reason,  # type: ignore[arg-type]
            last_mark_price=None if row.last_mark_price is None else Decimal(str(row.last_mark_price)),
            unrealized_pnl=None if row.unrealized_pnl is None else Decimal(str(row.unrealized_pnl)),
            realized_pnl=None if row.realized_pnl is None else Decimal(str(row.realized_pnl)),
            setup_name=row.setup_name,
            quality_score=None if row.quality_score is None else Decimal(str(row.quality_score)),
            updated_at=row.updated_at,
        )
