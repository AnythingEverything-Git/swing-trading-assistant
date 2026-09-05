"""Simple per-IP rate limits for heavy API routes (no auth yet)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-window limiter keyed by client IP + route group."""

    def __init__(self, app, *, limits: dict[str, tuple[int, float]] | None = None):
        super().__init__(app)
        # path_prefix -> (max_calls, window_seconds)
        self.limits = limits or {
            "/api/v1/scan/opportunities": (30, 60.0),
            "/api/v1/market-data/quotes": (120, 60.0),
            "/api/v1/research/": (60, 60.0),
        }
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _group(self, path: str) -> str | None:
        for prefix in self.limits:
            if path == prefix or path.startswith(prefix):
                return prefix
        return None

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        group = self._group(request.url.path)
        if group is None:
            return await call_next(request)

        max_calls, window = self.limits[group]
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{group}"
        now = time.monotonic()

        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= max_calls:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again shortly."},
                    headers={"Retry-After": str(int(window))},
                )
            bucket.append(now)

        return await call_next(request)
