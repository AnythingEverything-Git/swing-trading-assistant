"""FastAPI application entrypoint and minimal health endpoint."""
from fastapi import FastAPI
from .schemas import HealthCheck


def create_app() -> FastAPI:
    app = FastAPI(title="Swing Trading Assistant - Backend")

    @app.get("/health", response_model=HealthCheck)
    def health():
        return HealthCheck(status="ok")

    return app


app = create_app()
