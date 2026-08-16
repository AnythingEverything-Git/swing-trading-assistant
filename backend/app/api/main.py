"""FastAPI application entrypoint and health endpoints.

Includes a basic service health check and a database health check that uses
the infrastructure database session helper. The DB check is intentionally
lightweight and does not create tables or run migrations.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .schemas import HealthCheck
from ..core.config import get_settings
from ..infrastructure.database import session as db_session


def create_app() -> FastAPI:
    app = FastAPI(title="Swing Trading Assistant - Backend")

    @app.get("/health", response_model=HealthCheck)
    def health():
        return HealthCheck(status="ok")

    @app.get("/health/db")
    async def health_db():
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
