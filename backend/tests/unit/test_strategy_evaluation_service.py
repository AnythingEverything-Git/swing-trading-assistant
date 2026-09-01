from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.market_data import Candle
from app.domain.strategy.strategy import StrategyInput, StrategyResult, TradeCandidate
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider
from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService


class StubStrategy:
    def __init__(self, result: StrategyResult):
        self.result = result
        self.received_input: StrategyInput | None = None

    def evaluate(self, strategy_input: StrategyInput) -> StrategyResult:
        self.received_input = strategy_input
        return self.result


@pytest.mark.asyncio
async def test_service_passes_provider_candles_into_strategy_input():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    candles = [
        Candle(
            symbol="TST",
            exchange="TEST",
            instrument_id=1,
            timeframe="1d",
            timestamp=start,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=1000,
        ),
        Candle(
            symbol="TST",
            exchange="TEST",
            instrument_id=1,
            timeframe="1d",
            timestamp=start + timedelta(days=1),
            open=Decimal("100.5"),
            high=Decimal("101.5"),
            low=Decimal("99.5"),
            close=Decimal("101.0"),
            volume=1100,
        ),
    ]
    provider = MockMarketDataProvider(candles=candles)
    expected = StrategyResult(has_setup=False, status="NO_SETUP", reason="stubbed")
    strategy = StubStrategy(expected)

    result = await StrategyEvaluationService(provider, strategy).evaluate("TST", "1d", start, end)

    assert result is expected
    assert strategy.received_input is not None
    assert strategy.received_input.symbol == "TST"
    assert strategy.received_input.timeframe == "1d"
    assert strategy.received_input.candles == candles


@pytest.mark.asyncio
async def test_service_returns_strategy_result_unchanged():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    candle = Candle(
        symbol="TST",
        exchange="TEST",
        instrument_id=1,
        timeframe="1d",
        timestamp=start,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=1000,
    )
    candidate = TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("110.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="breakout",
    )
    expected = StrategyResult(has_setup=True, candidate=candidate, status="VALID_SETUP")
    provider = MockMarketDataProvider(candles=[candle])
    strategy = StubStrategy(expected)

    result = await StrategyEvaluationService(provider, strategy).evaluate("TST", "1d", start, end)

    assert result is expected
    assert result.candidate == candidate


@pytest.mark.asyncio
async def test_service_rejects_invalid_date_range():
    provider = MockMarketDataProvider(candles=[])
    strategy = StubStrategy(StrategyResult(has_setup=False, status="NO_SETUP"))
    service = StrategyEvaluationService(provider, strategy)

    with pytest.raises(ValueError, match="start.*end|end.*start"):
        await service.evaluate("TST", "1d", datetime(2024, 1, 2, tzinfo=timezone.utc), datetime(2024, 1, 1, tzinfo=timezone.utc))
