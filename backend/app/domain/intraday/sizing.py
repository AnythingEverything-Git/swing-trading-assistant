"""Position sizing and portfolio guards for ORB V1."""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from app.domain.intraday.config_v1 import IntradayConfigV1, DEFAULT_CONFIG_V1
from app.domain.intraday.types import FillPlan, PortfolioState


def size_quantity(
    *,
    equity: Decimal,
    effective_risk_per_share: Decimal,
    entry: Decimal,
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> int:
    if effective_risk_per_share <= 0 or entry <= 0:
        return 0
    allowed_risk = equity * config.risk_per_trade_pct
    qty = int((allowed_risk / effective_risk_per_share).to_integral_value(rounding=ROUND_DOWN))
    max_value = equity * config.max_position_value_pct
    max_by_value = int((max_value / entry).to_integral_value(rounding=ROUND_DOWN))
    return max(0, min(qty, max_by_value))


def can_open(
    state: PortfolioState,
    fill: FillPlan,
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> str | None:
    """Return lock reason or None if open is allowed."""
    if fill.symbol in state.traded_symbols:
        return "ORDER_REJECTED"
    if len(state.open_fills) >= config.max_concurrent:
        return "PORTFOLIO_RISK_LIMIT"
    open_risk = sum((f.risk_amount for f in state.open_fills), Decimal("0")) + fill.risk_amount
    if open_risk > state.equity * config.max_open_risk_pct:
        return "PORTFOLIO_RISK_LIMIT"
    if state.realized_pnl <= -(state.equity * config.daily_loss_lock_pct):
        return "DAILY_LOSS_LOCK"
    if state.consecutive_losses >= config.consecutive_loss_lock:
        return "CONSECUTIVE_LOSS_LOCK"
    return None


__all__ = ["size_quantity", "can_open"]
