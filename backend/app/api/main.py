"""FastAPI application entrypoint and health endpoints.

Includes a basic service health check and a database health check that uses
the infrastructure database session helper. The DB check is intentionally
lightweight and does not create tables or run migrations.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .schemas import HealthCheck
from ..core.config import get_settings
from ..infrastructure.database import session as db_session
from ..infrastructure.market_data.factory import UpstoxProviderFactory
from ..infrastructure.market_data.demo_provider import DemoMarketDataProvider
from ..infrastructure.market_data.source import live_ready, normalize_market_data_source
from ..application.market_data.refresh_scheduler import refresh_scheduler_loop, scheduler_should_run
from .routes import backtest, market_data, paper, product, research, scan, strategy

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create a FastAPI app and manage DB engine lifecycle using a lifespan.

    The app will create a single AsyncEngine and sessionmaker at startup and
    dispose the engine at shutdown. Both are attached to `app.state`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: create engine and sessionmaker from settings
        settings = get_settings()
        db_url = getattr(settings, "database_url", None)
        if not db_url:
            # Fail fast if DB not configured
            raise RuntimeError("Database not configured in Settings")

        engine = db_session.create_engine(db_url)
        sessionmaker = db_session.create_sessionmaker(engine)
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker

        source = normalize_market_data_source(getattr(settings, "market_data_source", "demo"))
        app.state.market_data_source = source
        app.state.upstox_factory = None
        app.state.upstox_provider = None
        app.state.ingest_provider = DemoMarketDataProvider()

        if source == "upstox":
            if not live_ready(settings):
                raise RuntimeError(
                    "MARKET_DATA_SOURCE=upstox requires UPSTOX_ACCESS_TOKEN. "
                    "Leave MARKET_DATA_SOURCE=demo until the token is available."
                )
            factory = UpstoxProviderFactory()
            provider = await factory.startup()
            app.state.upstox_factory = factory
            app.state.upstox_provider = provider
            app.state.ingest_provider = provider

        app.state.refresh_running = False
        app.state.refresh_stop_event = asyncio.Event()
        app.state.refresh_task = None
        if scheduler_should_run(settings):
            app.state.refresh_task = asyncio.create_task(
                refresh_scheduler_loop(app, app.state.refresh_stop_event),
                name="market-data-refresh-scheduler",
            )
            logger.info("Market-data refresh scheduler started")
        else:
            logger.info("Market-data refresh scheduler not started")

        from app.application.scan.scan_job_queue import get_or_create_scan_queue

        scan_queue = get_or_create_scan_queue(app)
        await scan_queue.start(app)

        try:
            yield
        finally:
            try:
                await scan_queue.stop()
            except Exception:
                logger.exception("Error while stopping scan job worker")

            stop_event = getattr(app.state, "refresh_stop_event", None)
            refresh_task = getattr(app.state, "refresh_task", None)
            if stop_event is not None:
                stop_event.set()
            if refresh_task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(refresh_task), timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    refresh_task.cancel()
                    try:
                        await refresh_task
                    except (asyncio.CancelledError, Exception):
                        pass
                except Exception:
                    logger.exception("Error while stopping market-data refresh scheduler")

            # Shutdown: dispose engine
            try:
                await engine.dispose()
            except Exception:
                pass
            # Shutdown Upstox factory if present
            factory = getattr(app.state, "upstox_factory", None)
            if factory is not None:
                try:
                    await factory.shutdown()
                except Exception:
                    pass

    app = FastAPI(title="Swing Trading Assistant - Backend", lifespan=lifespan)

    from .rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # include routers
    app.include_router(market_data.router)
    app.include_router(strategy.router)
    app.include_router(backtest.router)
    app.include_router(scan.router)
    app.include_router(product.router)
    app.include_router(research.router)
    app.include_router(paper.router)

    @app.get("/health", response_model=HealthCheck)
    def health():
        return HealthCheck(status="ok")

    @app.get("/health/db")
    async def health_db():
        # Simple health-check only; uses settings directly to avoid creating
        # transient engines here.
        settings = get_settings()
        db_url = getattr(settings, "database_url", None)
        if not db_url:
            return JSONResponse(status_code=500, content={"status": "error", "database": "not-configured"})
        try:
            await db_session.health_check(db_url)
            return {"status": "ok", "database": "ok"}
        except Exception as exc:  # pragma: no cover - behavior covered by unit tests using mocks
            return JSONResponse(status_code=503, content={"status": "error", "database": "down"})

    return app


app = create_app()
