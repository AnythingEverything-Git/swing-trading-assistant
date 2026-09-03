"""Product / data-source status for the UI freshness banner."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings, get_settings
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.market_data.source import (
    data_claim,
    live_ready,
    normalize_market_data_source,
)


@dataclass(frozen=True)
class ProductStatus:
    data_source: str
    live_ready: bool
    claim: str
    last_candle_time: datetime | None
    symbols_with_candles: int
    environment: str


class ProductStatusService:
    def __init__(self, candle_repo: CandleRepository, settings: Settings | None = None) -> None:
        self.candle_repo = candle_repo
        self.settings = settings or get_settings()

    async def status(self, timeframe: str = "1d") -> ProductStatus:
        last = await self.candle_repo.latest_timestamp(timeframe)
        count = await self.candle_repo.count_instruments(timeframe)
        return ProductStatus(
            data_source=normalize_market_data_source(self.settings.market_data_source),
            live_ready=live_ready(self.settings),
            claim=data_claim(self.settings),
            last_candle_time=last,
            symbols_with_candles=count,
            environment=self.settings.environment,
        )


__all__ = ["ProductStatus", "ProductStatusService"]
