"""ORM model for intraday ORB practice trades (stop-only + 15:10 flatten)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class IntradayPracticeTradeORM(Base):
    __tablename__ = "intraday_practice_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_mark_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(32), nullable=False)
