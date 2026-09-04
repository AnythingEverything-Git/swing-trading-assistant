"""ORM model for simulated paper trades."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class PaperTradeORM(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    target: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
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
    setup_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
