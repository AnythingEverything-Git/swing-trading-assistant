from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy, StrategyInput
from app.domain.market_data import Candle


def _build_valid_setup_series():
    candles = []
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
        (102.5, 102.8, 101.5, 102.0, 2300),
        (101.8, 102.0, 100.9, 101.5, 2100),
        (102.0, 102.4, 101.3, 101.7, 2200),
    ]
    for idx, (open_, high, low, close, volume) in enumerate(levels):
        candles.append(
            Candle(
                symbol="TST",
                exchange="TEST",
                instrument_id=1,
                timeframe="1d",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=idx),
                open=Decimal(str(open_)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=volume,
            )
        )
    return candles


def _as_of(candles, last_index):
    return candles[: last_index + 1]


def test_forming_awaiting_retest_when_last_bar_is_breakout():
    strategy = BreakoutRetestConfirmationStrategy()
    candles = _as_of(_build_valid_setup_series(), 19)
    strategy_input = StrategyInput(symbol="TST", timeframe="1d", candles=candles)

    assert strategy.evaluate(strategy_input).has_setup is False
    forming = strategy.inspect_forming(strategy_input)
    assert forming is not None
    assert forming.stage == "AWAITING_RETEST"
    assert forming.breakout_candle_index == 19
    assert forming.retest_candle_index is None


def test_forming_awaiting_confirmation_when_last_bar_is_retest():
    strategy = BreakoutRetestConfirmationStrategy()
    candles = _as_of(_build_valid_setup_series(), 20)
    strategy_input = StrategyInput(symbol="TST", timeframe="1d", candles=candles)

    assert strategy.evaluate(strategy_input).has_setup is False
    forming = strategy.inspect_forming(strategy_input)
    assert forming is not None
    assert forming.stage == "AWAITING_CONFIRMATION"
    assert forming.breakout_candle_index == 19
    assert forming.retest_candle_index == 20


def test_forming_is_none_when_now_setup_is_confirmed():
    strategy = BreakoutRetestConfirmationStrategy()
    candles = _as_of(_build_valid_setup_series(), 21)
    strategy_input = StrategyInput(symbol="TST", timeframe="1d", candles=candles)

    assert strategy.evaluate(strategy_input).has_setup is True
    assert strategy.inspect_forming(strategy_input) is None
