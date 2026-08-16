"""ORM model for daily candles.

Uses Numeric for price fields and timezone-aware DateTime for timestamps.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Integer, ForeignKey, String, DateTime, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class CandleORM(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "timestamp", name="uq_candle_instrument_timeframe_timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")

    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
