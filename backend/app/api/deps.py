from __future__ import annotations

from typing import AsyncGenerator
from fastapi import Request, Depends

from app.infrastructure.database import session as db_session
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.application.market_data.query_service import MarketDataQueryService
from typing import Optional

from app.infrastructure.market_data.mock_provider import MockMarketDataProvider


async def get_db(request: Request):
    """Yield an AsyncSession from the app.state.sessionmaker.

    This function assumes the application lifespan has already initialized
    `app.state.sessionmaker`. If the sessionmaker is not present, fail
    immediately rather than creating a transient engine per request.
    """
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if sessionmaker is None:
        raise RuntimeError("Database not configured: application startup did not initialize the DB sessionmaker")

    async with sessionmaker() as sess:
        try:
            yield sess
            await sess.commit()
        except Exception:
            await sess.rollback()
            raise


async def get_query_service(session=Depends(get_db)) -> MarketDataQueryService:
    inst_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    return MarketDataQueryService(inst_repo, candle_repo)


async def get_upstox_provider(request: Request):
    """Return the Upstox provider instance created at app startup.

    Tests can override this dependency to provide a mock provider.
    """
    provider = getattr(request.app.state, "upstox_provider", None)
    if provider is None:
        # fallback to a Mock provider for tests if nothing configured
        return MockMarketDataProvider()
    return provider


async def get_ingestion_service(session=Depends(get_db), provider=Depends(get_upstox_provider)):
    inst_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService

    return MarketDataIngestionService(provider, inst_repo, candle_repo)


async def get_strategy_evaluation_service(query_service: MarketDataQueryService = Depends(get_query_service)):
    from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    return StrategyEvaluationService(query_service, BreakoutRetestConfirmationStrategy())


async def get_backtest_service(query_service: MarketDataQueryService = Depends(get_query_service)):
    from app.application.backtesting.backtest_service import BacktestService
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    return BacktestService(query_service, BreakoutRetestConfirmationStrategy())


async def get_opportunity_scan_service(
    evaluation_service=Depends(get_strategy_evaluation_service),
):
    """Compose OpportunityScanService over persisted-candle StrategyEvaluationService.

    Candle source is MarketDataQueryService (PostgreSQL), not Demo/Upstox providers.
    """
    from app.application.scan.opportunity_scan_service import OpportunityScanService

    return OpportunityScanService(evaluation_service)
