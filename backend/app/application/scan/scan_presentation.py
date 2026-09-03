"""Rank, size, and narrate a universe scan without changing eligibility rules."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.application.backtesting.position_sizing import calculate_position_size
from app.application.narrative.template_narrator import (
    eligible_narrative,
    forming_narrative,
    invalidation_copy,
)
from app.application.scan.opportunity_scan_service import EligibleOpportunity
from app.application.scan.quality_score import QualityScore, score_opportunity
from app.application.scan.universe_scan_report_service import UniverseScanReport


@dataclass(frozen=True)
class PresentedOpportunity:
    opportunity: EligibleOpportunity
    quality: QualityScore
    rank: int
    narrative: str
    invalidation: str
    quantity: int | None
    risk_amount: Decimal | None


@dataclass(frozen=True)
class PresentedForming:
    forming: FormingSetup
    narrative: str


@dataclass(frozen=True)
class PresentedScan:
    report: UniverseScanReport
    opportunities: tuple[PresentedOpportunity, ...]
    top: tuple[PresentedOpportunity, ...]
    forming: tuple[PresentedForming, ...]


def present_scan(
    report: UniverseScanReport,
    *,
    account_equity: Decimal | None = None,
    risk_percent: Decimal | None = None,
    top_n: int = 5,
    min_score: Decimal | None = None,
) -> PresentedScan:
    ranked: list[PresentedOpportunity] = []
    scored = [
        (score_opportunity(item.candidate, item.evidence), item) for item in report.opportunities
    ]
    scored.sort(key=lambda pair: (-pair[0].score, pair[1].symbol))

    rank = 0
    for quality, item in scored:
        if min_score is not None and quality.score < min_score:
            continue
        rank += 1
        quantity = None
        risk_amount = None
        if account_equity is not None and risk_percent is not None:
            sizing = calculate_position_size(account_equity, risk_percent, item.candidate)
            quantity = sizing.quantity
            risk_amount = sizing.actual_risk_amount
        ranked.append(
            PresentedOpportunity(
                opportunity=item,
                quality=quality,
                rank=rank,
                narrative=eligible_narrative(item.candidate, item.evidence),
                invalidation=invalidation_copy(item.evidence),
                quantity=quantity,
                risk_amount=risk_amount,
            )
        )

    forming = tuple(
        PresentedForming(forming=item, narrative=forming_narrative(item))
        for item in report.forming
    )
    presented = tuple(ranked)
    n = max(0, top_n)
    return PresentedScan(
        report=report,
        opportunities=presented,
        top=presented[:n],
        forming=forming,
    )


__all__ = ["PresentedForming", "PresentedOpportunity", "PresentedScan", "present_scan"]
