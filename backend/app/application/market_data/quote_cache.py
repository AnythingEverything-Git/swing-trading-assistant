"""Short-TTL quote cache so interactive LTP reads stay ≤3s without changing values."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Same LTP within TTL is accuracy-preserving for desk refresh cadence.
_QUOTE_TTL_SEC = 5.0
# Soft stale window: still accurate prior LTP if Upstox is slow.
_QUOTE_STALE_MAX_SEC = 60.0
_FETCH_TIMEOUT_SEC = 2.2
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_inflight: dict[str, asyncio.Task] = {}


def _cache_key(symbols: list[str]) -> str:
    return ",".join(sorted(s.strip().upper() for s in symbols if s and s.strip()))


def _lookup(symbols: list[str], *, max_age: float) -> dict[str, dict[str, Any]] | None:
    key = _cache_key(symbols)
    hit = _cache.get(key)
    if hit is None:
        return None
    saved, payload = hit
    if (time.monotonic() - saved) > max_age:
        return None
    return {sym: dict(val) for sym, val in payload.items()}


def get_cached_quotes(symbols: list[str]) -> dict[str, dict[str, Any]] | None:
    return _lookup(symbols, max_age=_QUOTE_TTL_SEC)


def put_cached_quotes(symbols: list[str], payload: dict[str, dict[str, Any]]) -> None:
    key = _cache_key(symbols)
    _cache[key] = (time.monotonic(), {sym: dict(val) for sym, val in payload.items()})


async def fetch_quotes_cached(
    quote_fn,
    symbols: list[str],
    *,
    timeout_sec: float = _FETCH_TIMEOUT_SEC,
) -> dict[str, dict[str, Any]]:
    """Return quotes from TTL cache or Upstox; never wait longer than timeout_sec."""
    names = [s.strip().upper() for s in symbols if s and s.strip()]
    if not names:
        return {}

    cached = get_cached_quotes(names)
    if cached is not None:
        return cached

    key = _cache_key(names)

    async def _load() -> dict[str, dict[str, Any]]:
        raw = await quote_fn(names)
        if not isinstance(raw, dict):
            raw = {}
        put_cached_quotes(names, raw)
        return raw

    task = _inflight.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_load())
        _inflight[key] = task

    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout_sec)
    except asyncio.TimeoutError:
        stale = _lookup(names, max_age=_QUOTE_STALE_MAX_SEC)
        if stale is not None:
            logger.warning("quote fetch timed out; serving soft-stale LTP for %s", key)
            return stale
        logger.warning("quote fetch timed out after %.1fs for %s", timeout_sec, key)
        # Let background task finish so the next poll hits cache.
        return {}
    finally:
        if _inflight.get(key) is task and task.done():
            _inflight.pop(key, None)


__all__ = ["fetch_quotes_cached", "get_cached_quotes", "put_cached_quotes"]
