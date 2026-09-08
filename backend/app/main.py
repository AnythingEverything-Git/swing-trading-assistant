"""Application entrypoint for running the FastAPI app.

Uses the FastAPI app defined under `app.api.main`.

On Windows, prefer: `python run_api.py --port 8001`
(so psycopg gets SelectorEventLoop). Plain `uvicorn` may use ProactorEventLoop.
"""
from __future__ import annotations

from .api.main import app

__all__ = ["app"]
