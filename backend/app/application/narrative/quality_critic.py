"""Advisory quality critic — never replaces rules-based ranking."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.application.narrative.grounded_narrator import GroundedNarrator
from app.application.scan.quality_score import QualityScore
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate

_KNOWN_FLAGS = frozenset(
    {
        "weak_volume",
        "loose_retest",
        "thin_confirmation",
        "wide_risk",
        "tight_ok",
        "strong_volume",
    }
)


@dataclass(frozen=True)
class QualityCritique:
    critique: str | None
    flags: tuple[str, ...]
    provider: str


def _rules_flags(quality: QualityScore) -> tuple[str, ...]:
    flags: list[str] = []
    if quality.volume_thrust < Decimal("1.5"):
        flags.append("weak_volume")
    elif quality.volume_thrust >= Decimal("2.5"):
        flags.append("strong_volume")
    if quality.retest_tightness > Decimal("1.5"):
        flags.append("loose_retest")
    elif quality.retest_tightness <= Decimal("0.75"):
        flags.append("tight_ok")
    if quality.confirmation_volume_ratio < Decimal("1.2"):
        flags.append("thin_confirmation")
    if quality.risk_percent > Decimal("3"):
        flags.append("wide_risk")
    return tuple(flags)


def _template_critique(quality: QualityScore, flags: tuple[str, ...]) -> str:
    parts: list[str] = []
    if "weak_volume" in flags:
        parts.append(f"Breakout volume thrust is soft at {quality.volume_thrust}x SMA.")
    if "loose_retest" in flags:
        parts.append(f"Retest sits {quality.retest_tightness} ATR from structure — roomy.")
    if "thin_confirmation" in flags:
        parts.append(f"Confirmation volume is only {quality.confirmation_volume_ratio}x SMA.")
    if "wide_risk" in flags:
        parts.append(f"Stop risk is {quality.risk_percent}% of entry — wider than ideal.")
    if "strong_volume" in flags and "weak_volume" not in flags:
        parts.append(f"Volume thrust looks supportive at {quality.volume_thrust}x SMA.")
    if "tight_ok" in flags and "loose_retest" not in flags:
        parts.append(f"Retest is tight ({quality.retest_tightness} ATR).")
    if not parts:
        parts.append(f"Balanced components: {quality.reason}.")
    return " ".join(parts)


def quality_facts(
    candidate: TradeCandidate,
    evidence: StrategyEvidence,
    quality: QualityScore,
) -> dict[str, Any]:
    return {
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "score": str(quality.score),
        "volume_thrust": str(quality.volume_thrust),
        "confirmation_volume_ratio": str(quality.confirmation_volume_ratio),
        "retest_tightness": str(quality.retest_tightness),
        "risk_percent": str(quality.risk_percent),
        "quality_reason": quality.reason,
        "structure_level": str(getattr(evidence, "structure_level", evidence.resistance)),
        "retest_extreme": str(getattr(evidence, "retest_extreme", evidence.retest_low)),
        "atr_value": str(evidence.atr_value),
        "risk_reward_ratio": str(candidate.risk_reward_ratio),
    }


async def critique_opportunity(
    narrator: GroundedNarrator | None,
    *,
    candidate: TradeCandidate,
    evidence: StrategyEvidence,
    quality: QualityScore,
) -> QualityCritique:
    flags = _rules_flags(quality)
    fallback = _template_critique(quality, flags)
    if narrator is None or not narrator.enabled:
        return QualityCritique(critique=fallback, flags=flags, provider="template")

    facts = quality_facts(candidate, evidence, quality)
    facts["flags"] = list(flags)
    result = await narrator.rephrase_text(
        kind="quality_critique",
        source_text=fallback,
        facts=facts,
        instruction=(
            "Write one short advisory critique sentence for a trader. "
            "Do not change the rules score or invent new flags. "
            "Stay advisory — ranking authority remains the rules score."
        ),
    )
    return QualityCritique(
        critique=result.text or fallback,
        flags=flags,
        provider=result.provider,
    )


def sanitize_flags(raw: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not raw:
        return ()
    out: list[str] = []
    for item in raw:
        key = str(item).strip().lower()
        if key in _KNOWN_FLAGS and key not in out:
            out.append(key)
    return tuple(out)


__all__ = [
    "QualityCritique",
    "critique_opportunity",
    "quality_facts",
    "sanitize_flags",
]
