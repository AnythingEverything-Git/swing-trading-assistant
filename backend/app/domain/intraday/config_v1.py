"""Frozen CONFIG_V1 for NSE_STOCKS_ETF_ORB_RVOL_5M_V1.

Numeric changes require a new strategy version — do not tune in place.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal


STRATEGY_ID = "NSE_STOCKS_ETF_ORB_RVOL_5M_V1"
CONFIG_HASH = "CONFIG_V1"


@dataclass(frozen=True)
class IntradayConfigV1:
    strategy_id: str = STRATEGY_ID
    config_hash: str = CONFIG_HASH

    # Session clocks (IST, full session)
    or_start: time = time(9, 15)
    or_end: time = time(9, 20)  # exclusive
    entry_cutoff: time = time(14, 30)
    forced_exit: time = time(15, 10)

    # Screen
    min_rvol5: Decimal = Decimal("1.0")
    top_n: int = 20
    rvol_lookback_sessions: int = 14

    # Doji: max(1 tick, 0.05% of OR_OPEN)
    doji_pct: Decimal = Decimal("0.0005")

    # Stop
    atr_period: int = 14
    stop_atr_mult: Decimal = Decimal("0.10")
    stop_min_ticks: int = 3
    stop_min_pct: Decimal = Decimal("0.001")  # 0.10% of entry
    stop_min_spread_mult: Decimal = Decimal("1.5")
    stop_or_min_mult: Decimal = Decimal("0.25")
    stop_or_max_mult: Decimal = Decimal("1.50")
    risk_invalid_mult: Decimal = Decimal("1.25")

    # Slippage: max(1 tick, 2 bps)
    slip_bps: Decimal = Decimal("2")

    # Sizing / portfolio
    risk_per_trade_pct: Decimal = Decimal("0.005")  # 0.5%
    max_position_value_pct: Decimal = Decimal("0.10")
    max_concurrent: int = 3
    max_open_risk_pct: Decimal = Decimal("0.015")
    daily_loss_lock_pct: Decimal = Decimal("0.02")
    consecutive_loss_lock: int = 3

    # Liquidity
    min_adv_inr: Decimal = Decimal("50000000")  # ₹5 crore
    default_tick: Decimal = Decimal("0.05")
    # Reject if quote spread / mid > this (0.15% mid). Spec §1 liquidity gate.
    max_spread_pct: Decimal = Decimal("0.0015")


DEFAULT_CONFIG_V1 = IntradayConfigV1()


__all__ = ["STRATEGY_ID", "CONFIG_HASH", "IntradayConfigV1", "DEFAULT_CONFIG_V1"]
