from __future__ import annotations

from datetime import datetime
from typing import Sequence

from app.domain.market_data import Candle
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
        return self.evaluate_loaded(symbol, timeframe, candles)

    async def classify(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> tuple[StrategyResult, FormingSetup | None]:
        if start > end:
            raise ValueError("start must be less than or equal to end")

        candles = await self.market_data_provider.get_candles(symbol, timeframe, start, end)
        return self.classify_loaded(symbol, timeframe, candles)

    def evaluate_loaded(
        self, symbol: str, timeframe: str, candles: Sequence[Candle]
    ) -> StrategyResult:
        strategy_input = StrategyInput(symbol=symbol, timeframe=timeframe, candles=list(candles))
        return self.strategy.evaluate(strategy_input)

    def classify_loaded(
        self, symbol: str, timeframe: str, candles: Sequence[Candle]
    ) -> tuple[StrategyResult, FormingSetup | None]:
        strategy_input = StrategyInput(symbol=symbol, timeframe=timeframe, candles=list(candles))
        result = self.strategy.evaluate(strategy_input)
        inspect_forming = getattr(self.strategy, "inspect_forming", None)
        if inspect_forming is None:
            return result, None
        try:
            forming = inspect_forming(strategy_input, evaluated=result)
        except TypeError:
            # Strategies that do not accept evaluated= yet
            forming = None if result.has_setup else inspect_forming(strategy_input)
        return result, forming
