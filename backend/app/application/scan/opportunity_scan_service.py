"""Multi-symbol opportunity scan over the existing strategy evaluation path.

Orchestrates per-symbol evaluation only. Does not duplicate eligibility rules,
recalculate trade levels, or embed universe membership data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate
from app.domain.universe import StockUniverse


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
    """Scan symbols via StrategyEvaluationService; optionally source symbols from a StockUniverse."""

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
            # Deliberately do not catch evaluation failures: missing/incomplete market
            # data must not be misclassified as StrategyResult NO_SETUP.
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

    async def scan_universe(
        self,
        universe: StockUniverse,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> OpportunityScanResult:
        """Scan all constituents from a StockUniverse snapshot.

        Universe answers WHO to scan; eligibility remains StrategyEvaluationService /
        BreakoutRetestConfirmationStrategy.
        """
        snapshot = universe.get_snapshot()
        return await self.scan(snapshot.symbols, timeframe, start, end)


__all__ = [
    "EligibleOpportunity",
    "OpportunityScanResult",
    "OpportunityScanService",
]
