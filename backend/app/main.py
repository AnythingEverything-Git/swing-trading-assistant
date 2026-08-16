"""Application entrypoint for running the FastAPI app.

Uses the FastAPI app defined under `app.api.main`.
"""
from .api.main import app

__all__ = ["app"]
