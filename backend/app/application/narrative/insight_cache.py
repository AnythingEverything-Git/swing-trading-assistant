"""In-memory TTL cache for research insights (avoid Gemini regen on tab reopen)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from app.application.narrative.gemini_narrator import InsightResult, normalize_insight_context

_DEFAULT_TTL_SECONDS = 30 * 60
_lock = threading.Lock()
_CACHE: dict[str, tuple[float, InsightResult]] = {}


def insight_cache_key(symbol: str, tab: str, context: dict[str, Any]) -> str:
    """Stable key from symbol, tab, and normalized fact context (no live-only noise)."""
    normalized = normalize_insight_context(dict(context or {}))
    # Drop volatile live marks so quote ticks do not bust the cache.
    for volatile in ("current_price", "current_price_change_percent", "mark", "ltp"):
        normalized.pop(volatile, None)
    if isinstance(normalized.get("setup"), dict):
        setup = dict(normalized["setup"])
        setup.pop("current_price", None)
        setup.pop("current_price_change_percent", None)
        normalized["setup"] = setup
    blob = json.dumps(
        {"symbol": symbol.upper(), "tab": tab.lower(), "context": normalized},
        sort_keys=True,
        default=str,
        ensure_ascii=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]
    return f"{symbol.upper()}:{tab.lower()}:{digest}"


def get_cached_insight(key: str) -> InsightResult | None:
    now = time.monotonic()
    with _lock:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires_at, result = item
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        return result


def put_cached_insight(key: str, result: InsightResult, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
    with _lock:
        _CACHE[key] = (time.monotonic() + max(1, ttl_seconds), result)


def clear_insight_cache() -> None:
    with _lock:
        _CACHE.clear()


__all__ = [
    "insight_cache_key",
    "get_cached_insight",
    "put_cached_insight",
    "clear_insight_cache",
]
