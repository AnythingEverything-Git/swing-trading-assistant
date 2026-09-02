from datetime import datetime, timezone
from decimal import Decimal

from app.application.backtesting.backtest_models import BacktestTrade, ExitReason
from app.application.backtesting.performance_metrics import calculate_performance_metrics


def make_trade(pnl_per_share: str, r_multiple: str, quantity: int = 1) -> BacktestTrade:
    trade_time = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
    return BacktestTrade(
        symbol="TST",
        timeframe="1d",
        setup_time=trade_time,
        entry_time=trade_time,
        entry_price=Decimal("100"),
        stop_loss=Decimal("98"),
        target=Decimal("110"),
        exit_time=trade_time,
        exit_price=Decimal("100") + Decimal(pnl_per_share),
        exit_reason=ExitReason.TARGET,
        risk_per_share=Decimal("2"),
        r_multiple=Decimal(r_multiple),
        pnl_per_share=Decimal(pnl_per_share),
        quantity=quantity,
    )


def test_empty_trade_list_returns_zero_metrics():
    metrics = calculate_performance_metrics(())

    assert metrics.total_trades == 0
    assert metrics.winning_trades == 0
    assert metrics.losing_trades == 0
    assert metrics.win_rate == Decimal("0")
    assert metrics.total_pnl == Decimal("0")
    assert metrics.average_pnl == Decimal("0")
    assert metrics.total_r == Decimal("0")
    assert metrics.average_r == Decimal("0")
    assert metrics.maximum_drawdown == Decimal("0")


def test_all_winning_trades():
    metrics = calculate_performance_metrics((make_trade("5", "2.5"), make_trade("3", "1.5")))

    assert metrics.total_trades == 2
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 0
    assert metrics.win_rate == Decimal("100")
    assert metrics.total_pnl == Decimal("8")
    assert metrics.average_pnl == Decimal("4")
    assert metrics.total_r == Decimal("4")
    assert metrics.average_r == Decimal("2")


def test_all_losing_trades():
    metrics = calculate_performance_metrics((make_trade("-2", "-1"), make_trade("-4", "-2")))

    assert metrics.winning_trades == 0
    assert metrics.losing_trades == 2
    assert metrics.win_rate == Decimal("0")
    assert metrics.total_pnl == Decimal("-6")
    assert metrics.average_pnl == Decimal("-3")
    assert metrics.total_r == Decimal("-3")
    assert metrics.average_r == Decimal("-1.5")


def test_mixed_trades_and_zero_pnl_trade():
    metrics = calculate_performance_metrics(
        (make_trade("5", "2.5"), make_trade("-2", "-1"), make_trade("0", "0"))
    )

    assert metrics.total_trades == 3
    assert metrics.winning_trades == 1
    assert metrics.losing_trades == 1
    assert metrics.win_rate == Decimal("33.33333333333333333333333333")
    assert metrics.total_pnl == Decimal("3")
    assert metrics.average_pnl == Decimal("1")
    assert metrics.total_r == Decimal("1.5")
    assert metrics.average_r == Decimal("0.5")


def test_maximum_drawdown_uses_cumulative_pnl():
    metrics = calculate_performance_metrics(
        (make_trade("10", "5"), make_trade("-6", "-3"), make_trade("-8", "-4"), make_trade("12", "6"))
    )

    assert metrics.maximum_drawdown == Decimal("14")


def test_metrics_preserve_decimal_arithmetic():
    metrics = calculate_performance_metrics((make_trade("1.10", "0.55", quantity=3), make_trade("-0.20", "-0.10")))

    assert metrics.total_pnl == Decimal("3.10")
    assert metrics.average_pnl == Decimal("1.55")
    assert metrics.total_r == Decimal("0.45")