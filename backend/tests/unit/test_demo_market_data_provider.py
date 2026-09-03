"""Focused unit tests for DemoMarketDataProvider."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.market_data.demo_universe_seed_service import DEFAULT_DEMO_SEED_LOOKBACK_DAYS
from app.domain.market_data.provider import MarketDataProvider
from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy, StrategyInput
from app.infrastructure.market_data.demo_provider import (
    DemoMarketDataProvider,
    create_demo_market_data_provider,
)
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider


START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END_60 = START + timedelta(days=59)
END_120 = START + timedelta(days=119)
# Matches the default demo Nifty 500 seed window length (~9 months).
SEED_END = START + timedelta(days=DEFAULT_DEMO_SEED_LOOKBACK_DAYS)

_EXPLICIT_DEMO_SYMBOLS = (
    "DEMO_SETUP",
    "DEMO_SIDEWAYS",
    "DEMO_TREND",
    "DEMO_CHOP",
    "DEMO_DOWN",
)

# Symbols that previously failed seed with non-positive lows under additive downtrend drift.
_FORMERLY_FAILING_SYMBOLS = ("SBIN", "CIPLA", "ABBOTINDIA")


def _assert_positive_finite_ohlc(candles) -> None:
    for candle in candles:
        for value in (candle.open, candle.high, candle.low, candle.close):
            assert isinstance(value, Decimal)
            assert value.is_finite()
            assert value > 0
        assert candle.low <= candle.open <= candle.high
        assert candle.low <= candle.close <= candle.high
        assert candle.volume is not None and candle.volume > 0


@pytest.mark.asyncio
async def test_demo_provider_implements_market_data_provider_contract():
    provider = create_demo_market_data_provider()
    assert isinstance(provider, MarketDataProvider)
    assert isinstance(provider, DemoMarketDataProvider)

    candles = await provider.get_candles("DEMO_SIDEWAYS", "1d", START, END_60)
    assert isinstance(candles, list)
    assert len(candles) == 60


@pytest.mark.asyncio
async def test_demo_provider_is_deterministic_for_identical_inputs():
    provider = DemoMarketDataProvider()
    first = await provider.get_candles("INFY", "1d", START, END_60)
    second = await provider.get_candles("INFY", "1d", START, END_60)

    assert first == second
    assert [c.close for c in first] == [c.close for c in second]


@pytest.mark.asyncio
async def test_different_symbols_produce_different_deterministic_series():
    provider = DemoMarketDataProvider()
    left = await provider.get_candles("AAA", "1d", START, END_60)
    right = await provider.get_candles("BBB", "1d", START, END_60)

    assert [c.close for c in left] != [c.close for c in right]
    assert DemoMarketDataProvider.symbol_seed("AAA") != DemoMarketDataProvider.symbol_seed("BBB")


@pytest.mark.asyncio
async def test_requested_date_range_is_respected():
    provider = DemoMarketDataProvider()
    candles = await provider.get_candles("TCS", "1d", START, END_60)

    assert candles[0].timestamp == datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert candles[-1].timestamp == datetime(2023, 3, 1, tzinfo=timezone.utc)
    assert all(START <= c.timestamp <= END_60 for c in candles)
    for index in range(1, len(candles)):
        assert candles[index].timestamp == candles[index - 1].timestamp + timedelta(days=1)


@pytest.mark.asyncio
async def test_ohlc_invariants_and_positive_volume():
    provider = DemoMarketDataProvider()
    for symbol in (*_EXPLICIT_DEMO_SYMBOLS, "RELIANCE"):
        candles = await provider.get_candles(symbol, "1d", START, END_120)
        assert len(candles) == 120
        _assert_positive_finite_ohlc(candles)
        assert all(c.timeframe == "1d" and c.exchange == "DEMO" for c in candles)


@pytest.mark.asyncio
async def test_all_explicit_regimes_stay_positive_over_seed_length_range():
    provider = DemoMarketDataProvider()
    for symbol in _EXPLICIT_DEMO_SYMBOLS:
        candles = await provider.get_candles(symbol, "1d", START, SEED_END)
        assert len(candles) == DEFAULT_DEMO_SEED_LOOKBACK_DAYS + 1
        _assert_positive_finite_ohlc(candles)
        assert DemoMarketDataProvider.regime_for_symbol(symbol) in {
            "breakout_setup",
            "sideways",
            "uptrend",
            "choppy",
            "downtrend",
        }


@pytest.mark.asyncio
async def test_formerly_failing_symbols_stay_valid_over_seed_length_range():
    provider = DemoMarketDataProvider()
    for symbol in _FORMERLY_FAILING_SYMBOLS:
        assert DemoMarketDataProvider.regime_for_symbol(symbol) == "downtrend"
        candles = await provider.get_candles(symbol, "1d", START, SEED_END)
        assert len(candles) == DEFAULT_DEMO_SEED_LOOKBACK_DAYS + 1
        _assert_positive_finite_ohlc(candles)


@pytest.mark.asyncio
async def test_sufficient_history_for_long_ranges():
    provider = DemoMarketDataProvider()
    candles = await provider.get_candles("DEMO_TREND", "1d", START, START + timedelta(days=251))
    assert len(candles) == 252
    assert len(candles) > 20
    _assert_positive_finite_ohlc(candles)


@pytest.mark.asyncio
async def test_demo_setup_regime_exercises_existing_strategy_path():
    provider = DemoMarketDataProvider()
    assert DemoMarketDataProvider.regime_for_symbol("DEMO_SETUP") == "breakout_setup"

    candles = await provider.get_candles("DEMO_SETUP", "1d", START, END_60)
    assert len(candles) >= 22

    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="DEMO_SETUP", timeframe="1d", candles=candles)
    )

    assert result.has_setup is True
    assert result.candidate is not None
    assert result.evidence is not None
    assert result.candidate.direction == "LONG"
    assert result.candidate.entry_price == candles[-1].close
    assert result.evidence.confirmation_candle_index == len(candles) - 1
    assert result.candidate.risk_reward_ratio >= 2


@pytest.mark.asyncio
async def test_sideways_regime_does_not_force_a_setup():
    provider = DemoMarketDataProvider()
    candles = await provider.get_candles("DEMO_SIDEWAYS", "1d", START, END_60)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="DEMO_SIDEWAYS", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


@pytest.mark.asyncio
async def test_mock_provider_still_unchanged():
    mock = MockMarketDataProvider()
    candles = await mock.get_candles("TST", "1d", START, START + timedelta(days=2))
    assert len(candles) == 3


@pytest.mark.asyncio
async def test_unsupported_timeframe_raises():
    provider = DemoMarketDataProvider()
    with pytest.raises(ValueError, match="1d"):
        await provider.get_candles("DEMO_SETUP", "1h", START, END_60)
