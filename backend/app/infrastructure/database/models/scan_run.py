"""ORM model for ScanRun audit records.

Stores metadata about scan executions; does not store full instrument lists.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class ScanRunORM(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    universe_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    universe_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Avoid attribute name `metadata` which is reserved by DeclarativeBase.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    result_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
