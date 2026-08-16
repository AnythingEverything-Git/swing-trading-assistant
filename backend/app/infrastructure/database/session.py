"""Database session and engine scaffolding.

This module provides helpers to create an SQLAlchemy engine and sessionmaker.
Actual connection initialization will use `core.config` values.
"""
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import Optional
from sqlalchemy import text
import asyncio


def create_engine(db_url: str, echo: bool = False) -> AsyncEngine:
    """Create and return an async SQLAlchemy engine."""
    return create_async_engine(db_url, echo=echo)


def create_sessionmaker(engine: AsyncEngine) -> sessionmaker:
    """Return an async sessionmaker bound to the given engine."""
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def health_check(db_url: str, timeout_seconds: float = 5.0) -> bool:
    """Check database connectivity by creating an engine and executing a simple query.

    Returns True if the database responds to a trivial query within the timeout,
    otherwise raises the underlying exception.
    """
    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=timeout_seconds)
        return True
    finally:
        await engine.dispose()
