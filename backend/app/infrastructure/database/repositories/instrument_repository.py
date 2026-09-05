"""Instrument repository using SQLAlchemy AsyncSession.

Provides basic persistence operations for InstrumentORM.
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InstrumentORM


class InstrumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_symbol(self, symbol: str) -> Optional[InstrumentORM]:
        stmt = select(InstrumentORM).where(InstrumentORM.symbol == symbol)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_symbols(self, symbols: list[str]) -> list[InstrumentORM]:
        if not symbols:
            return []
        # Preserve case-sensitive NSE symbols as stored.
        unique = list(dict.fromkeys(symbols))
        stmt = select(InstrumentORM).where(InstrumentORM.symbol.in_(unique))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create(self, symbol: str, name: Optional[str] = None, exchange: Optional[str] = None, metadata: Optional[dict] = None) -> InstrumentORM:
        existing = await self.get_by_symbol(symbol)
        if existing:
            return existing

        inst = InstrumentORM(symbol=symbol, name=name, exchange=exchange, metadata_=metadata)
        self.session.add(inst)
        try:
            await self.session.flush()
            return inst
        except IntegrityError:
            await self.session.rollback()
            # Concurrent insert happened; fetch the existing record
            existing = await self.get_by_symbol(symbol)
            if existing:
                return existing
            raise
