from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.backtesting.backtest_service import BacktestService
from app.domain.market_data import Candle
from app.domain.strategy.strategy import (
    BreakoutRetestConfirmationStrategy,
    StrategyEvidence,
    StrategyResult,
    TradeCandidate,
)


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


def _build_two_independent_setup_series():
    """Deterministic series with two independent LONG Breakout→Retest→Confirmation setups.

    Setup 1 confirms at index 21 (entry 101.2). The next bar hits its 2R target so the
    first trade exits before setup 2. Setup 2 confirms at index 41 (entry 108.0).
    """
    levels = [
        (97.0, 97.5, 96.5, 96.8, 1200),
        (98.0, 98.9, 97.2, 97.6, 1200),
        (99.0, 99.8, 98.0, 98.4, 1200),
        (99.5, 100.0, 98.8, 99.3, 1200),
        (100.2, 100.6, 99.5, 99.9, 1200),
        (100.8, 101.5, 99.7, 100.6, 1300),
        (99.8, 100.3, 98.9, 99.2, 1300),
        (98.9, 99.2, 97.8, 98.5, 1300),
        (98.7, 99.0, 97.9, 98.2, 1200),
        (99.2, 99.6, 98.5, 98.9, 1200),
        (98.8, 99.3, 98.0, 98.5, 1200),
        (99.4, 99.9, 98.8, 99.1, 1200),
        (99.0, 99.4, 98.2, 98.6, 1200),
        (98.6, 98.9, 97.7, 98.3, 1200),
        (99.4, 99.8, 98.9, 99.1, 1200),
        (100.0, 100.3, 99.2, 99.6, 1400),
        (99.4, 99.8, 98.5, 98.9, 1300),
        (100.4, 101.0, 99.7, 100.2, 1300),
        (99.6, 100.0, 98.8, 99.2, 1300),
        (101.8, 102.2, 100.6, 101.1, 2000),
        (100.9, 101.0, 100.1, 100.5, 1500),
        (101.8, 102.2, 100.7, 101.2, 2200),
        (103.0, 107.5, 102.5, 107.0, 1800),
        (106.0, 106.5, 104.0, 104.5, 1400),
        (104.0, 104.5, 103.0, 103.5, 1400),
        (103.5, 104.0, 102.5, 103.0, 1400),
        (103.0, 105.0, 102.8, 104.5, 1500),
        (104.0, 104.8, 103.5, 104.0, 1400),
        (103.8, 104.2, 103.0, 103.5, 1400),
        (103.5, 104.0, 102.8, 103.2, 1400),
        (103.2, 103.8, 102.5, 103.0, 1400),
        (103.0, 103.5, 102.2, 102.8, 1400),
        (102.8, 103.2, 102.0, 102.5, 1400),
        (102.5, 103.0, 101.8, 102.2, 1400),
        (102.2, 102.8, 101.5, 102.0, 1400),
        (102.0, 104.5, 101.8, 104.0, 1500),
        (104.0, 106.0, 103.5, 105.0, 1600),
        (104.5, 105.2, 103.8, 104.2, 1500),
        (104.0, 104.8, 103.5, 104.0, 1500),
        (105.5, 108.0, 105.0, 107.5, 3000),
        (106.5, 107.0, 105.8, 106.2, 2000),
        (107.0, 108.5, 106.5, 108.0, 2800),
        (108.0, 115.0, 107.5, 114.0, 2500),
    ]
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            symbol="TST",
            exchange="TEST",
            instrument_id=1,
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            open=Decimal(str(open_)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=volume,
        )
        for index, (open_, high, low, close, volume) in enumerate(levels)
    ]


@pytest.mark.asyncio
async def test_backtest_real_strategy_produces_sequential_trades():
    candles = _build_two_independent_setup_series()
    strategy = BreakoutRetestConfirmationStrategy()

    result = await BacktestService(CandleProvider(candles), strategy).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
    )

    assert type(strategy) is BreakoutRetestConfirmationStrategy
    assert len(result.trades) == 2

    first, second = result.trades
    assert second.entry_time > first.exit_time
    assert first.quantity > 0
    assert second.quantity > 0
    assert first.risk_per_share > 0
    assert second.risk_per_share > 0
    assert first.entry_price == Decimal("101.2")
    assert second.entry_price == Decimal("108.0")


def _make_candidate_at(entry: str = "100", stop: str = "98", target: str = "105") -> TradeCandidate:
    return TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal(entry),
        stop_loss=Decimal(stop),
        target=Decimal(target),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="test",
    )


def _make_evidence_at(confirmation_index: int) -> StrategyEvidence:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return StrategyEvidence(
        resistance=Decimal("99"),
        breakout_candle_index=max(confirmation_index - 2, 0),
        breakout_candle_time=base + timedelta(days=max(confirmation_index - 2, 0)),
        retest_candle_index=max(confirmation_index - 1, 0),
        retest_candle_time=base + timedelta(days=max(confirmation_index - 1, 0)),
        confirmation_candle_index=confirmation_index,
        confirmation_candle_time=base + timedelta(days=confirmation_index),
        atr_value=Decimal("1"),
        volume_sma_value=Decimal("1000"),
        breakout_volume=1000,
        retest_low=Decimal("99"),
        confirmation_volume=1000,
        decision="test setup",
    )


class LastBarConfirmStrategy:
    """Stub that emits a setup only when the series ends exactly on a configured confirmation bar."""

    def __init__(self, confirmations: dict[int, TradeCandidate]):
        self.confirmations = confirmations

    def evaluate(self, strategy_input):
        confirmation_index = len(strategy_input.candles) - 1
        candidate = self.confirmations.get(confirmation_index)
        if candidate is None:
            return StrategyResult(has_setup=False)
        return StrategyResult(
            has_setup=True,
            candidate=candidate,
            evidence=_make_evidence_at(confirmation_index),
        )


@pytest.mark.asyncio
async def test_backtest_compounds_equity_after_winning_trade():
    # Confirm@2 -> target on bar 3 (+5/share). Confirm@5 uses same risk/share on higher equity.
    candles = make_candles(
        ["90", "95", "100", "105", "101", "100", "105"],
        highs=["91", "96", "101", "106", "102", "101", "106"],
        lows=["89", "94", "99", "104", "100", "99", "104"],
    )
    candidate = _make_candidate_at()
    strategy = LastBarConfirmStrategy({2: candidate, 5: candidate})

    result = await BacktestService(CandleProvider(candles), strategy).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    assert len(result.trades) == 2
    first, second = result.trades
    assert first.quantity == 50
    assert first.pnl_per_share == Decimal("5")
    assert first.exit_reason.value == "TARGET"
    # Equity becomes 10000 + 5*50 = 10250 → risk budget 102.50 → floor(102.50/2) = 51
    assert second.quantity == 51
    assert second.quantity > first.quantity


@pytest.mark.asyncio
async def test_backtest_compounds_equity_after_losing_trade():
    # Confirm@2 -> stop on bar 3 (-2/share). Confirm@5 uses same risk/share on lower equity.
    candles = make_candles(
        ["90", "95", "100", "99", "101", "100", "105"],
        highs=["91", "96", "101", "100", "102", "101", "106"],
        lows=["89", "94", "99", "97", "100", "99", "104"],
    )
    candidate = _make_candidate_at()
    strategy = LastBarConfirmStrategy({2: candidate, 5: candidate})

    result = await BacktestService(CandleProvider(candles), strategy).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    assert len(result.trades) == 2
    first, second = result.trades
    assert first.quantity == 50
    assert first.pnl_per_share == Decimal("-2")
    assert first.exit_reason.value == "STOP_LOSS"
    # Equity becomes 10000 - 2*50 = 9900 → risk budget 99 → floor(99/2) = 49
    assert second.quantity == 49
    assert second.quantity < first.quantity
