"""Absolute ₹ overrides on ORB sizing / can_open."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1
from app.domain.intraday.sizing import can_open, size_quantity
from app.domain.intraday.types import FillPlan, PortfolioState

IST = ZoneInfo("Asia/Kolkata")


def _fill(risk: str, symbol: str = "AAA") -> FillPlan:
    return FillPlan(
        symbol=symbol,
        direction="LONG",
        rank=1,
        entry=Decimal("100"),
        stop=Decimal("99"),
        quantity=10,
        stop_distance=Decimal("1"),
        effective_risk_per_share=Decimal("1"),
        trigger_bar_open=datetime(2026, 9, 11, 9, 25, tzinfo=IST),
        risk_amount=Decimal(risk),
    )


def test_size_quantity_respects_absolute_per_trade_cap():
    # 0.5% of 100000 = 500; absolute 200 caps qty
    qty = size_quantity(
        equity=Decimal("100000"),
        effective_risk_per_share=Decimal("10"),
        entry=Decimal("100"),
        config=DEFAULT_CONFIG_V1,
        max_risk_per_trade_inr=Decimal("200"),
    )
    assert qty == 20  # 200 / 10


def test_can_open_absolute_open_risk():
    state = PortfolioState(equity=Decimal("100000"), max_open_risk_inr=Decimal("3000"))
    # CONFIG max open = 1.5% of 100k = 1500; absolute 3000 would be looser — min uses 1500
    assert can_open(state, _fill("1400"), DEFAULT_CONFIG_V1, max_open_risk_inr=Decimal("3000")) is None
    assert (
        can_open(state, _fill("1600"), DEFAULT_CONFIG_V1, max_open_risk_inr=Decimal("3000"))
        == "PORTFOLIO_RISK_LIMIT"
    )


def test_can_open_absolute_daily_loss_tighter():
    state = PortfolioState(
        equity=Decimal("100000"),
        realized_pnl=Decimal("-2600"),
        daily_loss_lock_inr=Decimal("2500"),
    )
    # CONFIG daily = 2% = 2000; absolute 2500 is looser — min is 2000 so already locked
    assert (
        can_open(state, _fill("100"), DEFAULT_CONFIG_V1, daily_loss_lock_inr=Decimal("2500"))
        == "DAILY_LOSS_LOCK"
    )
    # Tighter absolute 500 vs % 2000
    state2 = PortfolioState(equity=Decimal("100000"), realized_pnl=Decimal("-600"))
    assert (
        can_open(state2, _fill("100"), DEFAULT_CONFIG_V1, daily_loss_lock_inr=Decimal("500"))
        == "DAILY_LOSS_LOCK"
    )
