"""Accuracy: OR-window first-5m aggregation matches full hist scan."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.intraday.session_service import _first_5m_volumes_by_session
from app.application.market_data.query_service import MarketDataQueryService
from app.domain.market_data import Candle
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.candle import CandleORM
from app.infrastructure.database.models.instrument import InstrumentORM
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository

IST = ZoneInfo("Asia/Kolkata")


def test_first_5m_repo_matches_python_scan():
    async def _test():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            inst = InstrumentORM(symbol="AAA", name="AAA", exchange="NSE")
            session.add(inst)
            await session.flush()

            day = date(2026, 9, 10)
            rows = []
            for minute, vol in [(15, 100), (16, 50), (17, 25), (18, 10), (19, 5)]:
                ts = datetime(day.year, day.month, day.day, 9, minute, tzinfo=IST)
                rows.append(
                    CandleORM(
                        instrument_id=inst.id,
                        timeframe="1m",
                        timestamp=ts,
                        open=Decimal("10"),
                        high=Decimal("10"),
                        low=Decimal("10"),
                        close=Decimal("10"),
                        volume=vol,
                    )
                )
            rows.append(
                CandleORM(
                    instrument_id=inst.id,
                    timeframe="1m",
                    timestamp=datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST),
                    open=Decimal("10"),
                    high=Decimal("10"),
                    low=Decimal("10"),
                    close=Decimal("10"),
                    volume=9999,
                )
            )
            session.add_all(rows)
            await session.commit()

            domain = [
                Candle(
                    symbol="AAA",
                    exchange="NSE",
                    instrument_id=inst.id,
                    timeframe="1m",
                    timestamp=r.timestamp,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    volume=r.volume,
                )
                for r in rows
            ]
            expected = _first_5m_volumes_by_session(domain)
            assert expected[day] == 190

            repo = CandleRepository(session)
            start = datetime(day.year, day.month, day.day, tzinfo=IST) - timedelta(days=1)
            end = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST) + timedelta(days=1)
            got = await repo.first_5m_volumes_by_instrument(
                [inst.id], start_timestamp=start, end_timestamp=end
            )
            assert got[inst.id][day] == expected[day]

            query = MarketDataQueryService(InstrumentRepository(session), repo)
            mapped = await query.get_first_5m_volumes_for_symbols(
                ["AAA"], hist_start=start, session_start=end
            )
            assert mapped["AAA"][day] == expected[day]
        await engine.dispose()

    asyncio.run(_test())
