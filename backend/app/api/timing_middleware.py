"""Request timing logs for Swing/Intraday SLA monitoring (p95 target < 3s)."""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.sla")

_PREFIXES = (
    "/api/v1/scan",
    "/api/v1/intraday",
    "/api/v1/universe",
    "/api/v1/strategy",
    "/api/v1/market-data",
    "/api/v1/alerts",
    "/api/v1/paper",
    "/api/v1/research",
)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _PREFIXES):
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        level = logging.WARNING if elapsed_ms >= 3000 else logging.INFO
        logger.log(
            level,
            "sla route=%s method=%s status=%s elapsed_ms=%.1f",
            path,
            request.method,
            getattr(response, "status_code", "?"),
            elapsed_ms,
        )
        return response
