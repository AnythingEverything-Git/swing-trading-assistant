from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.backtesting.backtest_service import BacktestService
from app.domain.market_data import Candle
from app.domain.strategy.strategy import StrategyEvidence, StrategyResult, TradeCandidate


def make_candles(closes: list[str], *, highs: list[str] | None = None, lows: list[str] | None = None):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            symbol="TST",
            exchange="TEST",
            instrument_id=1,
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            open=Decimal(close),
            high=Decimal(highs[index]) if highs else Decimal(close) + Decimal("1"),
            low=Decimal(lows[index]) if lows else Decimal(close) - Decimal("1"),
            close=Decimal(close),
            volume=1000,
        )
        for index, close in enumerate(closes)
    ]


def make_candidate() -> TradeCandidate:
    return TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("98"),
        target=Decimal("105"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="test",
    )


def make_evidence() -> StrategyEvidence:
    return StrategyEvidence(
        resistance=Decimal("99"),
        breakout_candle_index=0,
        breakout_candle_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        retest_candle_index=1,
        retest_candle_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        confirmation_candle_index=2,
        confirmation_candle_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        atr_value=Decimal("1"),
        volume_sma_value=Decimal("1000"),
        breakout_volume=1000,
        retest_low=Decimal("99"),
        confirmation_volume=1000,
        decision="test setup",
    )


class SignalStrategy:
    def evaluate(self, strategy_input):
        if len(strategy_input.candles) >= 3:
            return StrategyResult(has_setup=True, candidate=make_candidate(), evidence=make_evidence())
        return StrategyResult(has_setup=False)


class EmptyProvider:
    async def get_candles(self, symbol, timeframe, start, end):
        return []


class CandleProvider:
    def __init__(self, candles):
        self.candles = candles

    async def get_candles(self, symbol, timeframe, start, end):
        return self.candles


@pytest.mark.asyncio
async def test_backtest_closes_at_target_and_does_not_overlap_positions():
    candles = make_candles(["90", "95", "100", "101", "105", "110"])
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_price == Decimal("105")
    assert result.trades[0].quantity == 50
    assert result.trades[0].pnl_per_share == Decimal("5")


@pytest.mark.asyncio
async def test_backtest_stop_takes_precedence_when_both_levels_are_touched():
    candles = make_candles(
        ["90", "95", "100", "100"],
        highs=["91", "96", "101", "106"],
        lows=["89", "94", "99", "97"],
    )
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    assert result.trades[0].exit_reason.value == "STOP_LOSS"
    assert result.trades[0].exit_price == Decimal("98")


@pytest.mark.asyncio
async def test_backtest_closes_open_trade_at_end_of_data():
    candles = make_candles(["90", "95", "100", "102"])
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("1000"), Decimal("1")
    )

    assert result.trades[0].exit_reason.value == "END_OF_DATA"
    assert result.trades[0].exit_price == Decimal("102")
    assert result.trades[0].pnl_per_share == Decimal("2")


@pytest.mark.asyncio
async def test_backtest_skips_setup_confirmed_on_final_candle():
    candles = make_candles(["90", "95", "100"])
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("1000"), Decimal("1")
    )

    assert result.trades == ()


@pytest.mark.asyncio
async def test_backtest_returns_no_trades_when_position_size_is_zero():
    candles = make_candles(["90", "95", "100", "101"])
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("100"), Decimal("1")
    )

    assert result.trades == ()


@pytest.mark.asyncio
async def test_backtest_returns_no_trades_for_empty_history():
    result = await BacktestService(EmptyProvider(), SignalStrategy()).run(
        "TST", "1d", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2, tzinfo=timezone.utc), Decimal("10000"), Decimal("1")
    )

    assert result.trades == ()