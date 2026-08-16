"""Database session and engine scaffolding.

This module provides helpers to create an SQLAlchemy engine and sessionmaker.
Actual connection initialization will use `core.config` values.
"""
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import Optional


def create_engine(db_url: str, echo: bool = False) -> AsyncEngine:
    """Create and return an async SQLAlchemy engine."
    return create_async_engine(db_url, echo=echo)


def create_sessionmaker(engine: AsyncEngine) -> sessionmaker:
    """Return an async sessionmaker bound to the given engine."""
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
