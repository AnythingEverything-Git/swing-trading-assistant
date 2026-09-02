from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from app.domain.strategy.strategy import TradeCandidate


def _as_decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a valid decimal value")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal value") from exc
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal_value


@dataclass(frozen=True)
class PositionSizingResult:
    quantity: int
    maximum_risk_amount: Decimal
    actual_risk_amount: Decimal


def calculate_position_size(
    account_equity: Decimal | int | float | str,
    risk_percent: Decimal | int | float | str,
    candidate: TradeCandidate,
) -> PositionSizingResult:
    account_equity = _as_decimal(account_equity, "account_equity")
    risk_percent = _as_decimal(risk_percent, "risk_percent")
    risk_per_share = _as_decimal(candidate.risk_per_share, "risk_per_share")

    maximum_risk_amount = account_equity * risk_percent / Decimal("100")
    quantity = int((maximum_risk_amount / risk_per_share).to_integral_value(rounding=ROUND_FLOOR))
    actual_risk_amount = Decimal(quantity) * risk_per_share

    return PositionSizingResult(
        quantity=quantity,
        maximum_risk_amount=maximum_risk_amount,
        actual_risk_amount=actual_risk_amount,
    )


__all__ = ["PositionSizingResult", "calculate_position_size"]