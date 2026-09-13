"""Repository for intraday ORB practice trades."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.intraday.practice import IntradayPracticeTrade
from app.infrastructure.database.models.intraday_practice_trade import IntradayPracticeTradeORM


def _to_domain(row: IntradayPracticeTradeORM) -> IntradayPracticeTrade:
    return IntradayPracticeTrade(
        id=row.id,
        session_id=row.session_id,
        session_date=row.session_date,
        symbol=row.symbol,
        direction=row.direction,  # type: ignore[arg-type]
        entry_price=row.entry_price,
        stop_loss=row.stop_loss,
        quantity=row.quantity,
        risk_amount=row.risk_amount,
        status=row.status,  # type: ignore[arg-type]
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        exit_price=row.exit_price,
        exit_reason=row.exit_reason,  # type: ignore[arg-type]
        last_mark_price=row.last_mark_price,
        unrealized_pnl=row.unrealized_pnl,
        realized_pnl=row.realized_pnl,
        strategy_id=row.strategy_id,
        config_hash=row.config_hash,
    )


def _apply(row: IntradayPracticeTradeORM, trade: IntradayPracticeTrade) -> None:
    row.status = trade.status
    row.closed_at = trade.closed_at
    row.exit_price = trade.exit_price
    row.exit_reason = trade.exit_reason
    row.last_mark_price = trade.last_mark_price
    row.unrealized_pnl = trade.unrealized_pnl
    row.realized_pnl = trade.realized_pnl


class IntradayPracticeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, trade: IntradayPracticeTrade) -> IntradayPracticeTrade:
        row = IntradayPracticeTradeORM(
            session_id=trade.session_id,
            session_date=trade.session_date,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            quantity=trade.quantity,
            risk_amount=trade.risk_amount,
            status=trade.status,
            opened_at=trade.opened_at or datetime.now(timezone.utc),
            closed_at=trade.closed_at,
            exit_price=trade.exit_price,
            exit_reason=trade.exit_reason,
            last_mark_price=trade.last_mark_price,
            unrealized_pnl=trade.unrealized_pnl,
            realized_pnl=trade.realized_pnl,
            strategy_id=trade.strategy_id,
            config_hash=trade.config_hash,
        )
        self.session.add(row)
        await self.session.flush()
        trade.id = row.id
        return trade

    async def list_by_session(self, session_id: str) -> list[IntradayPracticeTrade]:
        result = await self.session.execute(
            select(IntradayPracticeTradeORM)
            .where(IntradayPracticeTradeORM.session_id == session_id)
            .order_by(IntradayPracticeTradeORM.id.desc())
        )
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_open(self, *, session_date: date | None = None) -> list[IntradayPracticeTrade]:
        stmt = select(IntradayPracticeTradeORM).where(IntradayPracticeTradeORM.status == "OPEN")
        if session_date is not None:
            stmt = stmt.where(IntradayPracticeTradeORM.session_date == session_date)
        result = await self.session.execute(stmt.order_by(IntradayPracticeTradeORM.id))
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_active_symbols(self, session_id: str) -> set[str]:
        result = await self.session.execute(
            select(IntradayPracticeTradeORM.symbol).where(
                IntradayPracticeTradeORM.session_id == session_id,
                IntradayPracticeTradeORM.status == "OPEN",
            )
        )
        return {str(s) for s in result.scalars().all()}

    async def delete_all(self) -> int:
        """Remove all intraday practice trades (fresh wallet)."""
        from sqlalchemy import delete

        result = await self.session.execute(delete(IntradayPracticeTradeORM))
        await self.session.flush()
        return int(result.rowcount or 0)

    async def save(self, trade: IntradayPracticeTrade) -> IntradayPracticeTrade:
        if trade.id is None:
            return await self.create(trade)
        row = await self.session.get(IntradayPracticeTradeORM, trade.id)
        if row is None:
            raise ValueError(f"practice trade {trade.id} not found")
        _apply(row, trade)
        await self.session.flush()
        return trade

    async def get(self, trade_id: int) -> IntradayPracticeTrade | None:
        row = await self.session.get(IntradayPracticeTradeORM, trade_id)
        return _to_domain(row) if row else None
