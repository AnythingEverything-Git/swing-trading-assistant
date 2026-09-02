from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.backtesting.backtest_models import (
    BacktestResult,
    BacktestSummary,
    BacktestTrade,
    ExitReason,
    PerformanceMetrics,
)


def make_trade(**overrides):
    trade_time = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
    base = {
        "symbol": "TST",
        "timeframe": "1d",
        "setup_time": trade_time,
        "entry_time": trade_time.replace(hour=10, minute=0),
        "entry_price": Decimal("100.00"),
        "stop_loss": Decimal("98.00"),
        "target": Decimal("110.00"),
        "exit_time": trade_time.replace(hour=11, minute=0),
        "exit_price": Decimal("109.00"),
        "exit_reason": ExitReason.TARGET,
        "risk_per_share": Decimal("2.00"),
        "r_multiple": Decimal("4.50"),
        "pnl_per_share": Decimal("9.00"),
        "quantity": 10,
    }
    base.update(overrides)
    return BacktestTrade(**base)


def test_valid_closed_trade():
    trade = make_trade()

    assert trade.symbol == "TST"
    assert trade.exit_reason == ExitReason.TARGET
    assert trade.r_multiple == Decimal("4.50")
    assert trade.pnl_per_share == Decimal("9.00")


def test_valid_open_trade():
    trade = make_trade(
        exit_time=None,
        exit_price=None,
        exit_reason=ExitReason.OPEN,
        r_multiple=None,
        pnl_per_share=None,
    )

    assert trade.exit_reason == ExitReason.OPEN
    assert trade.exit_time is None
    assert trade.exit_price is None
    assert trade.r_multiple is None
    assert trade.pnl_per_share is None


def test_invalid_long_stop_entry_target_relationship():
    with pytest.raises(ValueError):
        make_trade(stop_loss=Decimal("100.00"), entry_price=Decimal("100.00"))

    with pytest.raises(ValueError):
        make_trade(stop_loss=Decimal("101.00"), entry_price=Decimal("100.00"), target=Decimal("110.00"))


def test_invalid_negative_or_non_positive_prices():
    invalid_values = [Decimal("0"), Decimal("-1.00")]
    for value in invalid_values:
        with pytest.raises(ValueError):
            make_trade(entry_price=value)
        with pytest.raises(ValueError):
            make_trade(stop_loss=value)
        with pytest.raises(ValueError):
            make_trade(target=value)

    with pytest.raises(ValueError):
        make_trade(risk_per_share=Decimal("0"))


def test_invalid_incomplete_open_closed_trade_state():
    with pytest.raises(ValueError):
        make_trade(exit_time=None, exit_price=None, exit_reason=ExitReason.TARGET, r_multiple=None, pnl_per_share=None)

    with pytest.raises(ValueError):
        make_trade(exit_time=None, exit_price=Decimal("101.00"), exit_reason=ExitReason.TARGET, r_multiple=Decimal("1.00"), pnl_per_share=Decimal("1.00"))

    with pytest.raises(ValueError):
        make_trade(exit_time=datetime(2024, 1, 2, 12, tzinfo=timezone.utc), exit_price=None, exit_reason=ExitReason.OPEN, r_multiple=None, pnl_per_share=None)


def test_backtest_summary_accepts_deterministic_metric_values():
    summary = BacktestSummary(
        total_trades=10,
        winning_trades=6,
        losing_trades=3,
        open_trades=1,
        win_rate=Decimal("0.60"),
        average_win_r=Decimal("1.20"),
        average_loss_r=Decimal("-0.80"),
        expectancy_r=Decimal("0.40"),
        profit_factor=Decimal("2.00"),
        total_r=Decimal("8.00"),
        max_drawdown_r=Decimal("1.50"),
        max_consecutive_losses=2,
        average_holding_candles=Decimal("6.50"),
    )

    assert summary.total_trades == 10
    assert summary.win_rate == Decimal("0.60")
    assert summary.expectancy_r == Decimal("0.40")


def test_backtest_result_stores_trades_immutably():
    trade = make_trade()
    summary = BacktestSummary(
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        open_trades=0,
        win_rate=Decimal("1.00"),
        average_win_r=Decimal("4.50"),
        average_loss_r=Decimal("0"),
        expectancy_r=Decimal("4.50"),
        profit_factor=Decimal("1.00"),
        total_r=Decimal("4.50"),
        max_drawdown_r=Decimal("0"),
        max_consecutive_losses=0,
        average_holding_candles=Decimal("1.00"),
    )
    result = BacktestResult(
        symbol="TST",
        timeframe="1d",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        trades=(trade,),
        summary=summary,
    )

    assert result.trades == (trade,)
    assert isinstance(result.trades, tuple)
    with pytest.raises(FrozenInstanceError):
        result.trades = ()


def test_backtest_result_stores_optional_performance_metrics():
    metrics = PerformanceMetrics(1, 1, 0, Decimal("100"), Decimal("90"), Decimal("90"), Decimal("4.5"), Decimal("4.5"), Decimal("0"))
    result = BacktestResult(
        symbol="TST",
        timeframe="1d",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        trades=(),
        metrics=metrics,
    )

    assert result.metrics == metrics
