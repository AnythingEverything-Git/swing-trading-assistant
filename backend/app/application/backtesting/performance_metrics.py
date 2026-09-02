from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.application.backtesting.backtest_models import BacktestTrade, PerformanceMetrics


def calculate_performance_metrics(trades: Sequence[BacktestTrade]) -> PerformanceMetrics:
    total_trades = len(trades)
    zero = Decimal("0")
    if total_trades == 0:
        return PerformanceMetrics(0, 0, 0, zero, zero, zero, zero, zero, zero)

    pnls = [trade.pnl_per_share * trade.quantity for trade in trades]
    total_pnl = sum(pnls, zero)
    winning_trades = sum(pnl > zero for pnl in pnls)
    losing_trades = sum(pnl < zero for pnl in pnls)
    total_r = sum((trade.r_multiple for trade in trades), zero)
    cumulative_pnl = zero
    peak_pnl = zero
    maximum_drawdown = zero

    for pnl in pnls:
        cumulative_pnl += pnl
        peak_pnl = max(peak_pnl, cumulative_pnl)
        maximum_drawdown = max(maximum_drawdown, peak_pnl - cumulative_pnl)

    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=Decimal(winning_trades) / Decimal(total_trades) * Decimal("100"),
        total_pnl=total_pnl,
        average_pnl=total_pnl / Decimal(total_trades),
        total_r=total_r,
        average_r=total_r / Decimal(total_trades),
        maximum_drawdown=maximum_drawdown,
    )


__all__ = ["calculate_performance_metrics"]