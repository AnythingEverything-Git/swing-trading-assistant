"""Rules-based setup quality score from existing strategy evidence.

Does not invent prices. Used to rank ELIGIBLE names into a Top-N book.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate

_HUNDRED = Decimal("100")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class QualityScore:
    score: Decimal
    volume_thrust: Decimal
    confirmation_volume_ratio: Decimal
    retest_tightness: Decimal
    risk_percent: Decimal
    reason: str


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def score_opportunity(candidate: TradeCandidate, evidence: StrategyEvidence) -> QualityScore:
    volume_sma = evidence.volume_sma_value if evidence.volume_sma_value > 0 else Decimal("1")
    breakout_volume = Decimal(evidence.breakout_volume or 0)
    confirmation_volume = Decimal(evidence.confirmation_volume or 0)

    volume_thrust = breakout_volume / volume_sma
    confirmation_ratio = confirmation_volume / volume_sma
    if candidate.direction == "SHORT":
        retest_distance = evidence.retest_extreme - evidence.structure_level
        structure_label = "support"
    else:
        retest_distance = evidence.structure_level - evidence.retest_extreme
        structure_label = "resistance"
    retest_tightness = _clamp(retest_distance / evidence.atr_value, _ZERO, Decimal("3"))
    risk_percent = (candidate.risk_per_share / candidate.entry_price) * _HUNDRED

    volume_points = _clamp(volume_thrust / Decimal("3") * Decimal("30"), _ZERO, Decimal("30"))
    confirmation_points = _clamp(confirmation_ratio / Decimal("2.5") * Decimal("25"), _ZERO, Decimal("25"))
    tightness_points = _clamp((Decimal("1") - retest_tightness / Decimal("3")) * Decimal("25"), _ZERO, Decimal("25"))
    risk_points = _clamp((Decimal("5") - risk_percent) / Decimal("5") * Decimal("20"), _ZERO, Decimal("20"))
    score = _q(volume_points + confirmation_points + tightness_points + risk_points)

    reason = (
        f"volume thrust { _q(volume_thrust) }x, confirmation { _q(confirmation_ratio) }x SMA, "
        f"retest { _q(retest_tightness) } ATR from {structure_label}, risk { _q(risk_percent) }%"
    )
    return QualityScore(
        score=score,
        volume_thrust=_q(volume_thrust),
        confirmation_volume_ratio=_q(confirmation_ratio),
        retest_tightness=_q(retest_tightness),
        risk_percent=_q(risk_percent),
        reason=reason,
    )


__all__ = ["QualityScore", "score_opportunity"]
