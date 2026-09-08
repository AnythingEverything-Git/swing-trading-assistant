"""ORM model for persisted intraday ORB sessions."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Integer, Numeric, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class IntradaySessionORM(Base):
    __tablename__ = "intraday_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    data_source: Mapped[str] = mapped_column(String(16), nullable=False)
    equity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    coverage_eligible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fill_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    result_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
