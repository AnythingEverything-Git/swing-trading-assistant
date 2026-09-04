"""NSE corporate announcements and actions (fail-soft public endpoints)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger("app.news.nse")

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class NewsItem:
    title: str
    published_at: str | None
    source: str
    category: str
    url: str | None = None


@dataclass(frozen=True)
class NewsEventsSnapshot:
    symbol: str
    announcements: tuple[NewsItem, ...]
    events: tuple[NewsItem, ...]
    status: str
    detail: str | None = None


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if not hit:
        return None
    expires_at, value = hit
    if time.monotonic() > expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = (time.monotonic() + _CACHE_TTL_SECONDS, value)


class NseNewsProvider:
    """Fetch symbol announcements/events from NSE public JSON APIs."""

    def __init__(self, http_client: Any, timeout: float = 12.0) -> None:
        self._client = http_client
        self._timeout = timeout
        self._base = "https://www.nseindia.com"

    async def _warm_session(self) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self._base}/",
        }
        try:
            await self._client.get(self._base, headers=headers, timeout=self._timeout)
        except Exception as exc:
            logger.warning("nse.session_warm_failed: %s", exc)
        return headers

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        headers = await self._warm_session()
        url = f"{self._base}{path}"
        resp = await self._client.get(url, params=params, headers=headers, timeout=self._timeout)
        status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status is None or int(status) >= 400:
            raise RuntimeError(f"NSE HTTP {status}")
        payload = resp.json()
        return await payload if hasattr(payload, "__await__") else payload

    async def get_news_events(self, symbol: str) -> NewsEventsSnapshot:
        symbol = symbol.strip().upper()
        cache_key = f"nse:{symbol}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        announcements: list[NewsItem] = []
        events: list[NewsItem] = []
        try:
            ann_payload = await self._get_json(
                "/api/corporate-announcements",
                params={"index": "equities", "symbol": symbol},
            )
            rows = ann_payload if isinstance(ann_payload, list) else ann_payload.get("data", [])
            if isinstance(rows, list):
                for row in rows[:25]:
                    if not isinstance(row, dict):
                        continue
                    title = str(row.get("desc") or row.get("subject") or row.get("attchmntText") or "").strip()
                    if not title:
                        continue
                    announcements.append(
                        NewsItem(
                            title=title,
                            published_at=str(row.get("an_dt") or row.get("datetime") or "") or None,
                            source="NSE",
                            category="announcement",
                            url=str(row.get("attchmntFile") or "") or None,
                        )
                    )
        except Exception as exc:
            logger.warning("nse.announcements_failed symbol=%s err=%s", symbol, exc)
            snapshot = NewsEventsSnapshot(
                symbol=symbol,
                announcements=(),
                events=(),
                status="unavailable",
                detail=str(exc),
            )
            _cache_set(cache_key, snapshot)
            return snapshot

        try:
            today = date.today()
            actions_payload = await self._get_json(
                "/api/corporates-corporateActions",
                params={
                    "index": "equities",
                    "from_date": today.strftime("%d-%m-%Y"),
                    "to_date": (today + timedelta(days=90)).strftime("%d-%m-%Y"),
                },
            )
            action_rows = (
                actions_payload if isinstance(actions_payload, list) else actions_payload.get("data", [])
            )
            if isinstance(action_rows, list):
                for row in action_rows:
                    if not isinstance(row, dict):
                        continue
                    row_symbol = str(row.get("symbol") or row.get("symbol_name") or "").upper()
                    if row_symbol and row_symbol != symbol:
                        continue
                    subject = str(row.get("subject") or row.get("purpose") or "Corporate action").strip()
                    events.append(
                        NewsItem(
                            title=subject,
                            published_at=str(row.get("exDate") or row.get("recordDate") or "") or None,
                            source="NSE",
                            category=str(row.get("series") or "event"),
                            url=None,
                        )
                    )
        except Exception as exc:
            logger.warning("nse.actions_failed symbol=%s err=%s", symbol, exc)

        snapshot = NewsEventsSnapshot(
            symbol=symbol,
            announcements=tuple(announcements[:20]),
            events=tuple(events[:20]),
            status="ok",
            detail=None,
        )
        _cache_set(cache_key, snapshot)
        return snapshot


__all__ = ["NewsEventsSnapshot", "NewsItem", "NseNewsProvider"]
