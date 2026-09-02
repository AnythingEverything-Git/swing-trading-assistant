from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.application.backtesting.position_sizing import calculate_position_size
from app.domain.strategy.strategy import TradeCandidate


def make_candidate(risk_per_share: Decimal = Decimal("2.50")) -> TradeCandidate:
    return TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("100.00") - risk_per_share,
        target=Decimal("110.00"),
        risk_per_share=risk_per_share,
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="breakout",
    )


def test_normal_position_sizing():
    result = calculate_position_size(Decimal("10000"), Decimal("1"), make_candidate())

    assert result.quantity == 40
    assert result.maximum_risk_amount == Decimal("100")
    assert result.actual_risk_amount == Decimal("100.00")


def test_fractional_position_size_is_floored():
    result = calculate_position_size(Decimal("10000"), Decimal("1"), make_candidate(Decimal("3")))

    assert result.quantity == 33
    assert result.actual_risk_amount == Decimal("99")


def test_position_size_returns_zero_when_risk_budget_is_less_than_one_share():
    result = calculate_position_size(Decimal("100"), Decimal("1"), make_candidate(Decimal("2")))

    assert result.quantity == 0
    assert result.maximum_risk_amount == Decimal("1")
    assert result.actual_risk_amount == Decimal("0")


@pytest.mark.parametrize("account_equity", [Decimal("0"), Decimal("-1"), True, "invalid"])
def test_invalid_account_equity_is_rejected(account_equity):
    with pytest.raises(ValueError):
        calculate_position_size(account_equity, Decimal("1"), make_candidate())


@pytest.mark.parametrize("risk_percent", [Decimal("0"), Decimal("-1"), False, "invalid"])
def test_invalid_risk_percent_is_rejected(risk_percent):
    with pytest.raises(ValueError):
        calculate_position_size(Decimal("10000"), risk_percent, make_candidate())


@pytest.mark.parametrize("risk_per_share", [Decimal("0"), Decimal("-1"), True])
def test_invalid_risk_per_share_is_rejected(risk_per_share):
    with pytest.raises((TypeError, ValueError)):
        calculate_position_size(
            Decimal("10000"),
            Decimal("1"),
            SimpleNamespace(risk_per_share=risk_per_share),
        )


def test_position_sizing_uses_exact_decimal_arithmetic():
    result = calculate_position_size(Decimal("12345.67"), Decimal("0.75"), make_candidate(Decimal("1.23")))

    assert result.maximum_risk_amount == Decimal("92.592525")
    assert result.quantity == 75
    assert result.actual_risk_amount == Decimal("92.25")