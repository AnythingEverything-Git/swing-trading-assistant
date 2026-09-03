"""Universe scan report with per-symbol outcome classification.

Reuses StrategyEvaluationService for eligibility. Does not modify
OpportunityScanService fail-fast semantics — this facade catches per-symbol
failures so one missing series cannot abort the whole universe, and never
maps data failures to NO_SETUP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from app.application.scan.opportunity_scan_service import EligibleOpportunity
from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
from app.domain.strategy.strategy import FormingSetup
from app.domain.universe import StockUniverse

SymbolScanStatus = Literal["ELIGIBLE", "FORMING", "NO_SETUP", "UNAVAILABLE", "ERROR"]

_DEFAULT_ISSUE_LIMIT = 50


@dataclass(frozen=True)
class SymbolScanIssue:
    symbol: str
    status: Literal["UNAVAILABLE", "ERROR"]
    detail: str


@dataclass(frozen=True)
class UniverseScanReport:
    symbols_scanned: int
    eligible_count: int
    no_setup_count: int
    unavailable_count: int
    error_count: int
    opportunities: tuple[EligibleOpportunity, ...]
    issues: tuple[SymbolScanIssue, ...]
    forming_count: int = 0
    forming: tuple[FormingSetup, ...] = ()


class UniverseScanReportService:
    """Classify every universe symbol without aborting on data gaps."""

    def __init__(
        self,
        evaluation_service: StrategyEvaluationService,
        *,
        issue_limit: int = _DEFAULT_ISSUE_LIMIT,
    ) -> None:
        self.evaluation_service = evaluation_service
        self.issue_limit = issue_limit

    async def scan_universe(
        self,
        universe: StockUniverse,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> UniverseScanReport:
        snapshot = universe.get_snapshot()
        return await self.scan(snapshot.symbols, timeframe, start, end)

    async def scan(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> UniverseScanReport:
        opportunities: list[EligibleOpportunity] = []
        forming: list[FormingSetup] = []
        issues: list[SymbolScanIssue] = []
        no_setup_count = 0
        unavailable_count = 0
        error_count = 0
        symbols_scanned = 0

        for symbol in symbols:
            symbols_scanned += 1
            try:
                classify = getattr(self.evaluation_service, "classify", None)
                if classify is not None:
                    result, forming_setup = await classify(symbol, timeframe, start, end)
                else:
                    result = await self.evaluation_service.evaluate(symbol, timeframe, start, end)
                    forming_setup = None
            except ValueError as exc:
                unavailable_count += 1
                if len(issues) < self.issue_limit:
                    issues.append(
                        SymbolScanIssue(symbol=symbol, status="UNAVAILABLE", detail=str(exc))
                    )
                continue
            except Exception as exc:  # noqa: BLE001 — classify unexpected per-symbol failures
                error_count += 1
                if len(issues) < self.issue_limit:
                    issues.append(SymbolScanIssue(symbol=symbol, status="ERROR", detail=str(exc)))
                continue

            if result.has_setup and result.candidate is not None and result.evidence is not None:
                opportunities.append(
                    EligibleOpportunity(
                        symbol=symbol,
                        candidate=result.candidate,
                        evidence=result.evidence,
                    )
                )
                continue

            if forming_setup is not None:
                forming.append(forming_setup)
                continue

            no_setup_count += 1

        return UniverseScanReport(
            symbols_scanned=symbols_scanned,
            eligible_count=len(opportunities),
            no_setup_count=no_setup_count,
            unavailable_count=unavailable_count,
            error_count=error_count,
            opportunities=tuple(opportunities),
            issues=tuple(issues),
            forming_count=len(forming),
            forming=tuple(forming),
        )


__all__ = [
    "SymbolScanIssue",
    "SymbolScanStatus",
    "UniverseScanReport",
    "UniverseScanReportService",
]
