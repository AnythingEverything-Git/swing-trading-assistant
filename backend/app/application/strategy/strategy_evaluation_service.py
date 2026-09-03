from __future__ import annotations

from datetime import datetime

from app.domain.market_data.provider import MarketDataProvider
from app.domain.strategy.strategy import FormingSetup, Strategy, StrategyInput, StrategyResult


class StrategyEvaluationService:
    def __init__(self, market_data_provider: MarketDataProvider, strategy: Strategy) -> None:
        self.market_data_provider = market_data_provider
        self.strategy = strategy

    async def evaluate(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> StrategyResult:
        if start > end:
            raise ValueError("start must be less than or equal to end")

        candles = await self.market_data_provider.get_candles(symbol, timeframe, start, end)
        strategy_input = StrategyInput(symbol=symbol, timeframe=timeframe, candles=candles)
        return self.strategy.evaluate(strategy_input)

    async def classify(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> tuple[StrategyResult, FormingSetup | None]:
        if start > end:
            raise ValueError("start must be less than or equal to end")

        candles = await self.market_data_provider.get_candles(symbol, timeframe, start, end)
        strategy_input = StrategyInput(symbol=symbol, timeframe=timeframe, candles=candles)
        result = self.strategy.evaluate(strategy_input)
        inspect_forming = getattr(self.strategy, "inspect_forming", None)
        forming = inspect_forming(strategy_input) if inspect_forming is not None else None
        return result, forming
