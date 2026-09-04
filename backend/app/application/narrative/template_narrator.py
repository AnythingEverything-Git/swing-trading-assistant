"""Evidence-grounded narratives. Never invent Entry / SL / Target."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.domain.strategy.strategy import FormingSetup, StrategyEvidence, TradeCandidate


def _inr(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"₹{quantized}"


def _day(value: datetime) -> str:
    return value.date().isoformat()


def eligible_narrative(candidate: TradeCandidate, evidence: StrategyEvidence) -> str:
    risk_pct = (candidate.risk_per_share / candidate.entry_price * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if candidate.direction == "SHORT":
        return (
            f"{candidate.symbol} confirmed breakdown → retest → confirmation on {_day(evidence.confirmation_candle_time)}. "
            f"Close {_inr(candidate.entry_price)} broke support {_inr(evidence.structure_level)} "
            f"after a retest high of {_inr(evidence.retest_extreme)}. "
            f"Stop {_inr(candidate.stop_loss)} ({risk_pct}% of price). "
            f"Target {_inr(candidate.target)} at {candidate.risk_reward_ratio.quantize(Decimal('0.01'))}R."
        )
    return (
        f"{candidate.symbol} confirmed breakout → retest → confirmation on {_day(evidence.confirmation_candle_time)}. "
        f"Close {_inr(candidate.entry_price)} cleared resistance {_inr(evidence.structure_level)} "
        f"after a retest low of {_inr(evidence.retest_extreme)}. "
        f"Stop {_inr(candidate.stop_loss)} ({risk_pct}% of price). "
        f"Target {_inr(candidate.target)} at {candidate.risk_reward_ratio.quantize(Decimal('0.01'))}R."
    )


def invalidation_copy(evidence: StrategyEvidence) -> str:
    if evidence.direction == "SHORT":
        return (
            f"Short setup invalidates if the next daily close is above the retest high of "
            f"{_inr(evidence.retest_extreme)} (structurally back over support {_inr(evidence.structure_level)})."
        )
    return (
        f"Long setup invalidates if the next daily close is below the retest low of "
        f"{_inr(evidence.retest_extreme)} (structurally back under resistance {_inr(evidence.structure_level)})."
    )


def forming_narrative(forming: FormingSetup) -> str:
    level = forming.resistance
    if forming.direction == "SHORT":
        if forming.stage == "AWAITING_RETEST":
            return (
                f"{forming.symbol} printed a volume breakdown on {_day(forming.breakout_candle_time)} "
                f"below support {_inr(level)}. "
                f"Retest window: {forming.bars_remaining} bar(s) remaining. No trade plan until confirmation."
            )
        retest_extreme = forming.retest_low
        retest_time = forming.retest_candle_time
        assert retest_extreme is not None and retest_time is not None
        return (
            f"{forming.symbol} broke down and retested support {_inr(level)} "
            f"(retest high {_inr(retest_extreme)} on {_day(retest_time)}). "
            f"Waiting for a confirmation close; {forming.bars_remaining} bar(s) remaining. No Entry/SL/Target yet."
        )

    if forming.stage == "AWAITING_RETEST":
        return (
            f"{forming.symbol} printed a volume breakout on {_day(forming.breakout_candle_time)} "
            f"above resistance {_inr(level)}. "
            f"Retest window: {forming.bars_remaining} bar(s) remaining. No trade plan until confirmation."
        )
    retest_low = forming.retest_low
    retest_time = forming.retest_candle_time
    assert retest_low is not None and retest_time is not None
    return (
        f"{forming.symbol} broke out and retested resistance {_inr(level)} "
        f"(retest low {_inr(retest_low)} on {_day(retest_time)}). "
        f"Waiting for a confirmation close; {forming.bars_remaining} bar(s) remaining. No Entry/SL/Target yet."
    )


__all__ = ["eligible_narrative", "forming_narrative", "invalidation_copy"]
