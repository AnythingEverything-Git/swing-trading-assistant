"""Build morning/EOD AI briefs from a presented scan (grounded)."""
from __future__ import annotations

from typing import Any

from app.application.narrative.grounded_narrator import GroundedNarrator, GroundedTextResult
from app.application.scan.scan_presentation import PresentedScan


def _template_brief(presented: PresentedScan, *, mode: str, data_claim: str) -> str:
    label = "EOD" if mode == "eod" else "Premarket"
    lines = [
        f"{label} brief — {presented.report.eligible_count} eligible, "
        f"{presented.report.forming_count} forming. {data_claim}",
    ]
    if not presented.top:
        lines.append("No Top setups in this scan.")
        return " ".join(lines)
    for item in presented.top[:5]:
        c = item.opportunity.candidate
        lines.append(
            f"{item.rank}. {item.opportunity.symbol} {c.direction} "
            f"score {item.quality.score} R:R {c.risk_reward_ratio} — {item.narrative}"
        )
    return "\n".join(lines)


async def build_scan_brief(
    narrator: GroundedNarrator | None,
    presented: PresentedScan,
    *,
    mode: str = "premarket",
    data_claim: str,
) -> GroundedTextResult:
    fallback = _template_brief(presented, mode=mode, data_claim=data_claim)
    top_facts = []
    for item in presented.top[:5]:
        c = item.opportunity.candidate
        top_facts.append(
            {
                "rank": item.rank,
                "symbol": item.opportunity.symbol,
                "direction": c.direction,
                "score": str(item.quality.score),
                "risk_reward_ratio": str(c.risk_reward_ratio),
                "entry": str(c.entry_price),
                "stop": str(c.stop_loss),
                "target": str(c.target),
                "narrative": item.narrative,
                "quality_reason": item.quality.reason,
            }
        )
    facts: dict[str, Any] = {
        "mode": mode,
        "data_claim": data_claim,
        "eligible_count": presented.report.eligible_count,
        "forming_count": presented.report.forming_count,
        "symbols_scanned": presented.report.symbols_scanned,
        "top": top_facts,
        "forming_symbols": [item.forming.symbol for item in presented.forming[:8]],
        "source_text": fallback,
    }
    if narrator is None or not narrator.enabled:
        return GroundedTextResult(text=fallback, provider="template", grounded=True)
    return await narrator.rephrase_text(
        kind=f"scan_brief_{mode}",
        source_text=fallback,
        facts=facts,
        instruction=(
            "Write a short trader brief: one regime/context sentence, then one bullet per Top name. "
            "Use only the JSON facts. Do not invent prices."
        ),
    )


__all__ = ["build_scan_brief"]
