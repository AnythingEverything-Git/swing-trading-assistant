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
from app.infrastructure.market_data.deterministic_setup_series import (
    build_two_independent_setup_series,
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
async def test_backtest_gap_through_stop_fills_at_open():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=0), open=Decimal("90"), high=Decimal("91"), low=Decimal("89"), close=Decimal("90"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=1), open=Decimal("95"), high=Decimal("96"), low=Decimal("94"), close=Decimal("95"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=2), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=3), open=Decimal("96"), high=Decimal("97"), low=Decimal("95"), close=Decimal("96"), volume=1000),
    ]
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    trade = result.trades[0]
    assert trade.exit_reason.value == "GAP_THROUGH_STOP"
    assert trade.exit_price == Decimal("96")
    assert trade.exit_price != trade.stop_loss
    assert trade.pnl_per_share == Decimal("-4")


@pytest.mark.asyncio
async def test_backtest_gap_through_target_fills_at_open():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=0), open=Decimal("90"), high=Decimal("91"), low=Decimal("89"), close=Decimal("90"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=1), open=Decimal("95"), high=Decimal("96"), low=Decimal("94"), close=Decimal("95"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=2), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=3), open=Decimal("107"), high=Decimal("108"), low=Decimal("106"), close=Decimal("107"), volume=1000),
    ]
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    trade = result.trades[0]
    assert trade.exit_reason.value == "GAP_THROUGH_TARGET"
    assert trade.exit_price == Decimal("107")
    assert trade.exit_price != trade.target
    assert trade.pnl_per_share == Decimal("7")


@pytest.mark.asyncio
async def test_backtest_normal_stop_still_fills_at_stop_loss():
    candles = make_candles(
        ["90", "95", "100", "99"],
        highs=["91", "96", "101", "100"],
        lows=["89", "94", "99", "97"],
    )
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    assert result.trades[0].exit_reason.value == "STOP_LOSS"
    assert result.trades[0].exit_price == Decimal("98")


@pytest.mark.asyncio
async def test_backtest_normal_target_still_fills_at_target():
    candles = make_candles(
        ["90", "95", "100", "104"],
        highs=["91", "96", "101", "106"],
        lows=["89", "94", "99", "103"],
    )
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST", "1d", candles[0].timestamp, candles[-1].timestamp, Decimal("10000"), Decimal("1")
    )

    assert result.trades[0].exit_reason.value == "TARGET"
    assert result.trades[0].exit_price == Decimal("105")


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


@pytest.mark.asyncio
async def test_backtest_real_strategy_produces_sequential_trades():
    candles = build_two_independent_setup_series()
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
    # Bar 3 open stays between stop and target so this remains a normal TARGET fill, not a gap.
    candles = make_candles(
        ["90", "95", "100", "104", "101", "100", "104"],
        highs=["91", "96", "101", "106", "102", "101", "106"],
        lows=["89", "94", "99", "103", "100", "99", "103"],
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
    # Equity curve: 10000 → 9900 after first loss; peak 10000 → DD 100
    assert result.metrics is not None
    assert result.metrics.maximum_drawdown == Decimal("100")


@pytest.mark.asyncio
async def test_backtest_zero_slippage_and_cost_preserve_existing_pnl():
    candles = make_candles(
        ["90", "95", "100", "104"],
        highs=["91", "96", "101", "106"],
        lows=["89", "94", "99", "103"],
    )
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        slippage_per_share=Decimal("0"),
        cost_per_trade=Decimal("0"),
    )

    trade = result.trades[0]
    assert trade.entry_price == Decimal("100")
    assert trade.exit_price == Decimal("105")
    assert trade.pnl_per_share == Decimal("5")
    assert trade.exit_reason.value == "TARGET"


@pytest.mark.asyncio
async def test_backtest_slippage_worsens_long_entry_and_exit():
    # Signal entry 100, raw target exit 105; slippage 1 → entry 101, exit 104, pnl/share 3
    candles = make_candles(
        ["90", "95", "100", "104"],
        highs=["91", "96", "101", "106"],
        lows=["89", "94", "99", "103"],
    )
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        slippage_per_share=Decimal("1"),
    )

    trade = result.trades[0]
    assert trade.entry_price == Decimal("101")
    assert trade.exit_price == Decimal("104")
    assert trade.pnl_per_share == Decimal("3")
    assert trade.r_multiple == Decimal("3") / Decimal("2")


@pytest.mark.asyncio
async def test_backtest_flat_round_trip_cost_reduces_net_pnl_per_share():
    # qty 50, gross (105-100)*50 = 250, cost 5 → net 245 → pnl/share 4.9
    candles = make_candles(
        ["90", "95", "100", "104"],
        highs=["91", "96", "101", "106"],
        lows=["89", "94", "99", "103"],
    )
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        cost_per_trade=Decimal("5"),
    )

    trade = result.trades[0]
    assert trade.quantity == 50
    assert trade.pnl_per_share == Decimal("4.9")
    assert trade.r_multiple == Decimal("4.9") / Decimal("2")


@pytest.mark.asyncio
async def test_backtest_slippage_and_cost_are_reflected_in_equity_compounding():
    # First trade: entry 101, exit 104, qty 50, cost 5 → net = 3*50 - 5 = 145
    # Equity 10145 → second trade risk budget 101.45 → floor(101.45/2) = 50
    # Without costs/slippage second qty would be 51 after +250.
    candles = make_candles(
        ["90", "95", "100", "104", "101", "100", "104"],
        highs=["91", "96", "101", "106", "102", "101", "106"],
        lows=["89", "94", "99", "103", "100", "99", "103"],
    )
    candidate = _make_candidate_at()
    strategy = LastBarConfirmStrategy({2: candidate, 5: candidate})

    result = await BacktestService(CandleProvider(candles), strategy).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        slippage_per_share=Decimal("1"),
        cost_per_trade=Decimal("5"),
    )

    assert len(result.trades) == 2
    first, second = result.trades
    assert first.pnl_per_share == Decimal("2.9")  # (3*50 - 5) / 50
    assert first.quantity == 50
    assert second.quantity == 50
    assert second.quantity < 51


@pytest.mark.asyncio
async def test_backtest_gap_through_stop_applies_exit_slippage_to_open():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=0), open=Decimal("90"), high=Decimal("91"), low=Decimal("89"), close=Decimal("90"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=1), open=Decimal("95"), high=Decimal("96"), low=Decimal("94"), close=Decimal("95"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=2), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=3), open=Decimal("96"), high=Decimal("97"), low=Decimal("95"), close=Decimal("96"), volume=1000),
    ]
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        slippage_per_share=Decimal("1"),
    )

    trade = result.trades[0]
    assert trade.exit_reason.value == "GAP_THROUGH_STOP"
    assert trade.entry_price == Decimal("101")
    assert trade.exit_price == Decimal("95")  # open 96 - slippage 1
    assert trade.pnl_per_share == Decimal("-6")


@pytest.mark.asyncio
async def test_backtest_gap_through_target_applies_exit_slippage_to_open():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=0), open=Decimal("90"), high=Decimal("91"), low=Decimal("89"), close=Decimal("90"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=1), open=Decimal("95"), high=Decimal("96"), low=Decimal("94"), close=Decimal("95"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=2), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=start + timedelta(days=3), open=Decimal("107"), high=Decimal("108"), low=Decimal("106"), close=Decimal("107"), volume=1000),
    ]
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        slippage_per_share=Decimal("1"),
    )

    trade = result.trades[0]
    assert trade.exit_reason.value == "GAP_THROUGH_TARGET"
    assert trade.entry_price == Decimal("101")
    assert trade.exit_price == Decimal("106")  # open 107 - slippage 1
    assert trade.pnl_per_share == Decimal("5")


@pytest.mark.asyncio
async def test_backtest_end_of_data_applies_exit_slippage():
    candles = make_candles(["90", "95", "100", "102"])
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("1000"),
        Decimal("1"),
        slippage_per_share=Decimal("1"),
    )

    trade = result.trades[0]
    assert trade.exit_reason.value == "END_OF_DATA"
    assert trade.entry_price == Decimal("101")
    assert trade.exit_price == Decimal("101")  # close 102 - 1
    assert trade.pnl_per_share == Decimal("0")


@pytest.mark.asyncio
async def test_backtest_skips_trade_when_slippage_breaks_entry_invariant():
    candles = make_candles(
        ["90", "95", "100", "104"],
        highs=["91", "96", "101", "106"],
        lows=["89", "94", "99", "103"],
    )
    # entry 100 + 6 = 106 is not < target 105
    result = await BacktestService(CandleProvider(candles), SignalStrategy()).run(
        "TST",
        "1d",
        candles[0].timestamp,
        candles[-1].timestamp,
        Decimal("10000"),
        Decimal("1"),
        slippage_per_share=Decimal("6"),
    )

    assert result.trades == ()
