"""FastAPI application entrypoint and health endpoints.

Includes a basic service health check and a database health check that uses
the infrastructure database session helper. The DB check is intentionally
lightweight and does not create tables or run migrations.
"""
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .schemas import HealthCheck
from ..core.config import get_settings
from ..infrastructure.database import session as db_session
from ..core.config import get_settings
from ..infrastructure.market_data.factory import UpstoxProviderFactory
from ..infrastructure.market_data.demo_provider import DemoMarketDataProvider
from ..infrastructure.market_data.source import live_ready, normalize_market_data_source
from .routes import backtest, market_data, product, research, scan, strategy


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

        try:
            yield
        finally:
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
