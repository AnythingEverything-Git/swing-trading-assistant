"""Post-present_scan AI enrichment (why / invalidation / critic / data issues).

Never mutates Entry / SL / Target / rank order. Template text kept when LLM off/fails.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import httpx

from app.application.narrative.data_quality_copilot import explain_data_issues
from app.application.narrative.grounded_narrator import GroundedNarrator, narrative_llm_enabled
from app.application.narrative.quality_critic import critique_opportunity
from app.application.scan.scan_presentation import PresentedOpportunity, PresentedScan
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.scan.ai_enrich")


def _candidate_facts(item: PresentedOpportunity) -> dict[str, Any]:
    c = item.opportunity.candidate
    e = item.opportunity.evidence
    return {
        "symbol": item.opportunity.symbol,
        "direction": c.direction,
        "entry": str(c.entry_price),
        "stop": str(c.stop_loss),
        "target": str(c.target),
        "risk_reward_ratio": str(c.risk_reward_ratio),
        "risk_per_share": str(c.risk_per_share),
        "structure_level": str(getattr(e, "structure_level", e.resistance)),
        "retest_extreme": str(getattr(e, "retest_extreme", e.retest_low)),
        "atr_value": str(e.atr_value),
        "breakout_volume": e.breakout_volume,
        "confirmation_volume": e.confirmation_volume,
        "volume_sma_value": str(e.volume_sma_value),
        "confirmation_candle_time": e.confirmation_candle_time.isoformat(),
        "quality_score": str(item.quality.score),
        "quality_reason": item.quality.reason,
        "volume_thrust": str(item.quality.volume_thrust),
        "confirmation_volume_ratio": str(item.quality.confirmation_volume_ratio),
        "retest_tightness": str(item.quality.retest_tightness),
        "risk_percent": str(item.quality.risk_percent),
        "decision": e.decision,
    }


async def enrich_presented_scan(
    presented: PresentedScan,
    *,
    settings: Settings | None = None,
    polish_top_only: bool = True,
    http_client: Any | None = None,
) -> tuple[PresentedScan, list[str] | None, str | None]:
    """Return enriched scan + optional data-quality bullets + provider label."""
    cfg = settings or get_settings()
    issues = [
        {"symbol": i.symbol, "status": i.status, "detail": i.detail}
        for i in presented.report.issues
    ]

    if not narrative_llm_enabled(cfg):
        enriched_ops: list[PresentedOpportunity] = []
        for item in presented.opportunities:
            if polish_top_only and item not in presented.top:
                enriched_ops.append(item)
                continue
            critique = await critique_opportunity(
                None,
                candidate=item.opportunity.candidate,
                evidence=item.opportunity.evidence,
                quality=item.quality,
            )
            enriched_ops.append(
                replace(
                    item,
                    quality_critique=critique.critique,
                    quality_flags=critique.flags,
                )
            )
        by_rank = {item.rank: item for item in enriched_ops}
        top = tuple(by_rank[item.rank] for item in presented.top if item.rank in by_rank)
        dq = await explain_data_issues(None, issues=issues)
        return (
            PresentedScan(
                report=presented.report,
                opportunities=tuple(enriched_ops),
                top=top,
                forming=presented.forming,
            ),
            list(dq.bullets) if issues else None,
            "template",
        )

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=30.0)
    try:
        narrator = GroundedNarrator(client, cfg)
        targets = list(presented.top) if polish_top_only else list(presented.opportunities)
        target_symbols = {item.opportunity.symbol for item in targets}
        enriched: list[PresentedOpportunity] = []
        for item in presented.opportunities:
            if item.opportunity.symbol not in target_symbols:
                enriched.append(item)
                continue
            facts = _candidate_facts(item)
            why = await narrator.rephrase_text(
                kind="scan_why",
                source_text=item.narrative,
                facts=facts,
                instruction=(
                    "Explain why this setup is eligible in plain English. "
                    "Keep every price and ratio identical to the facts."
                ),
            )
            inv = await narrator.rephrase_text(
                kind="scan_invalidation",
                source_text=item.invalidation,
                facts=facts,
                instruction=(
                    "Explain the invalidation rule clearly. "
                    "Do not invent new levels — only retest/structure from facts."
                ),
            )
            critique = await critique_opportunity(
                narrator,
                candidate=item.opportunity.candidate,
                evidence=item.opportunity.evidence,
                quality=item.quality,
            )
            enriched.append(
                replace(
                    item,
                    narrative=why.text or item.narrative,
                    invalidation=inv.text or item.invalidation,
                    narrative_source=why.provider if why.provider == "llm" else "template",
                    invalidation_source=inv.provider if inv.provider == "llm" else "template",
                    quality_critique=critique.critique,
                    quality_flags=critique.flags,
                )
            )
        by_rank = {item.rank: item for item in enriched}
        top = tuple(by_rank[item.rank] for item in presented.top if item.rank in by_rank)
        dq = await explain_data_issues(narrator, issues=issues)
        provider = "llm" if any(i.narrative_source == "llm" for i in top) else "template"
        return (
            PresentedScan(
                report=presented.report,
                opportunities=tuple(enriched),
                top=top,
                forming=presented.forming,
            ),
            list(dq.bullets) if (issues or dq.bullets) else None,
            provider,
        )
    except Exception:
        logger.exception("scan.ai_enrich_failed")
        return presented, None, "template"
    finally:
        if owns_client:
            await client.aclose()


def opportunity_components_for_payload(item: PresentedOpportunity) -> dict[str, str]:
    return {
        "volume_thrust": str(item.quality.volume_thrust),
        "retest_tightness": str(item.quality.retest_tightness),
        "risk_percent": str(item.quality.risk_percent),
        "confirmation_volume_ratio": str(item.quality.confirmation_volume_ratio),
    }


__all__ = ["enrich_presented_scan", "opportunity_components_for_payload"]
