"""Multi-symbol opportunity scan over the existing strategy evaluation path.

Orchestrates per-symbol evaluation only. Does not duplicate eligibility rules,
recalculate trade levels, or load a market universe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate


@dataclass(frozen=True)
class EligibleOpportunity:
    """One symbol currently eligible for a swing trade, with existing strategy outputs."""

    symbol: str
    candidate: TradeCandidate
    evidence: StrategyEvidence


@dataclass(frozen=True)
class OpportunityScanResult:
    symbols_scanned: int
    eligible_count: int
    opportunities: tuple[EligibleOpportunity, ...]


class OpportunityScanService:
    """Scan an explicit symbol list using StrategyEvaluationService unchanged."""

    def __init__(self, evaluation_service: StrategyEvaluationService) -> None:
        self.evaluation_service = evaluation_service

    async def scan(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> OpportunityScanResult:
        opportunities: list[EligibleOpportunity] = []
        symbols_scanned = 0

        for symbol in symbols:
            symbols_scanned += 1
            result = await self.evaluation_service.evaluate(symbol, timeframe, start, end)
            if not result.has_setup:
                continue
            if result.candidate is None or result.evidence is None:
                continue
            opportunities.append(
                EligibleOpportunity(
                    symbol=symbol,
                    candidate=result.candidate,
                    evidence=result.evidence,
                )
            )

        return OpportunityScanResult(
            symbols_scanned=symbols_scanned,
            eligible_count=len(opportunities),
            opportunities=tuple(opportunities),
        )


__all__ = [
    "EligibleOpportunity",
    "OpportunityScanResult",
    "OpportunityScanService",
]
