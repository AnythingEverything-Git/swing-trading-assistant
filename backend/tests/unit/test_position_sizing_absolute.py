"""Absolute ₹ risk caps for swing position sizing."""
from __future__ import annotations

from decimal import Decimal

from app.application.backtesting.position_sizing import calculate_position_size
from app.domain.strategy.strategy import TradeCandidate


def _candidate() -> TradeCandidate:
    return TradeCandidate(
        symbol="TEST",
        timeframe="1d",
        direction="LONG",
        setup_name="test",
        entry_price=Decimal("100"),
        stop_loss=Decimal("98"),
        target=Decimal("104"),
        risk_per_share=Decimal("2"),
        reward=Decimal("4"),
        risk_reward_ratio=Decimal("2"),
    )


def test_absolute_cap_tighter_than_percent():
    # 1% of 350000 = 3500; absolute 2500 wins
    sized = calculate_position_size(
        Decimal("350000"),
        Decimal("1"),
        _candidate(),
        max_risk_amount=Decimal("2500"),
    )
    assert sized.maximum_risk_amount == Decimal("2500")
    assert sized.quantity == 1250  # 2500 / 2


def test_percent_tighter_than_absolute():
    sized = calculate_position_size(
        Decimal("350000"),
        Decimal("0.5"),
        _candidate(),
        max_risk_amount=Decimal("10000"),
    )
    assert sized.maximum_risk_amount == Decimal("1750")  # 0.5% of 350k
