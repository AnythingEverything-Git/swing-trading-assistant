"""ORM model for instruments.

Infrastructure-level model only; domain entities remain unchanged.
"""
from typing import Optional
from sqlalchemy import String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class InstrumentORM(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # `metadata` is a reserved attribute on Declarative classes; map the
    # column to a different attribute name to avoid conflicts while keeping
    # the column name as `metadata`.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
