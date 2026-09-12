"""Product / data-source status for the UI freshness banner."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import Settings, get_settings
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.market_data.source import (
    data_claim,
    live_ready,
    normalize_market_data_source,
)

# Process-wide cache (candle max/count are global). Accuracy preserved within TTL.
_STATUS_CACHE_TTL_SEC = 20.0
_status_cache: dict[str, tuple[float, "ProductStatus"]] = {}


def _stale_risk(*, live: bool, source: str, last_1d: datetime | None) -> str:
    if source == "demo" or not live:
        return "High"
    if last_1d is None:
        return "High"
    now = datetime.now(timezone.utc)
    ts = last_1d if last_1d.tzinfo else last_1d.replace(tzinfo=timezone.utc)
    age_hours = (now - ts.astimezone(timezone.utc)).total_seconds() / 3600
    if age_hours > 72:
        return "High"
    if age_hours > 36:
        return "Medium"
    return "Low"


@dataclass(frozen=True)
class ProductStatus:
    data_source: str
    live_ready: bool
    claim: str
    last_candle_time: datetime | None
    symbols_with_candles: int
    environment: str
    symbols_with_1m: int = 0
    last_1m_candle_time: datetime | None = None
    stale_risk: str = "High"


class ProductStatusService:
    def __init__(self, candle_repo: CandleRepository, settings: Settings | None = None) -> None:
        self.candle_repo = candle_repo
        self.settings = settings or get_settings()

    async def status(self, timeframe: str = "1d") -> ProductStatus:
        cache_key = timeframe
        hit = _status_cache.get(cache_key)
        now = time.monotonic()
        if hit is not None and (now - hit[0]) < _STATUS_CACHE_TTL_SEC:
            return hit[1]

        # Sequential queries only — AsyncSession forbids concurrent ops on one session
        # (asyncio.gather here caused 500s under load).
        last_1d = await self.candle_repo.latest_timestamp("1d")
        count_1d = await self.candle_repo.count_instruments("1d")
        last_1m = await self.candle_repo.latest_timestamp("1m")
        count_1m = await self.candle_repo.count_instruments("1m")
        source = normalize_market_data_source(self.settings.market_data_source)
        ready = live_ready(self.settings)
        result = ProductStatus(
            data_source=source,
            live_ready=ready,
            claim=data_claim(self.settings),
            last_candle_time=last_1d if timeframe == "1d" else (last_1m or last_1d),
            symbols_with_candles=count_1d,
            environment=self.settings.environment,
            symbols_with_1m=count_1m,
            last_1m_candle_time=last_1m,
            stale_risk=_stale_risk(live=ready, source=source, last_1d=last_1d),
        )
        _status_cache[cache_key] = (now, result)
        return result


__all__ = ["ProductStatus", "ProductStatusService"]
