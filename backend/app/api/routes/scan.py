"""Thin FastAPI surface for Nifty 500 opportunity scans over persisted candles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_opportunity_scan_service
from app.api.schemas import (
    EligibleOpportunityResponse,
    OpportunityScanRequest,
    OpportunityScanResponse,
    StrategyCandidateResponse,
    StrategyEvidenceResponse,
)
from app.application.scan.opportunity_scan_service import OpportunityScanService
from app.infrastructure.universe import Nifty500Universe

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])

_SUPPORTED_TIMEFRAMES = frozenset({"1d"})


@router.post("/opportunities", response_model=OpportunityScanResponse)
async def scan_opportunities(
    payload: OpportunityScanRequest,
    svc: OpportunityScanService = Depends(get_opportunity_scan_service),
) -> OpportunityScanResponse:
    if payload.start > payload.end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if payload.timeframe not in _SUPPORTED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="timeframe must be '1d'")

    universe = Nifty500Universe()
    snapshot = universe.get_snapshot()

    try:
        result = await svc.scan_universe(universe, payload.timeframe, payload.start, payload.end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    opportunities = [
        EligibleOpportunityResponse(
            symbol=opp.symbol,
            candidate=StrategyCandidateResponse(
                symbol=opp.candidate.symbol,
                timeframe=opp.candidate.timeframe,
                direction=opp.candidate.direction,
                entry_price=opp.candidate.entry_price,
                stop_loss=opp.candidate.stop_loss,
                target=opp.candidate.target,
                risk_per_share=opp.candidate.risk_per_share,
                reward=opp.candidate.reward,
                risk_reward_ratio=opp.candidate.risk_reward_ratio,
                setup_name=opp.candidate.setup_name,
            ),
            evidence=StrategyEvidenceResponse(
                resistance=opp.evidence.resistance,
                breakout_candle_index=opp.evidence.breakout_candle_index,
                breakout_candle_time=opp.evidence.breakout_candle_time,
                retest_candle_index=opp.evidence.retest_candle_index,
                retest_candle_time=opp.evidence.retest_candle_time,
                confirmation_candle_index=opp.evidence.confirmation_candle_index,
                confirmation_candle_time=opp.evidence.confirmation_candle_time,
                atr_value=opp.evidence.atr_value,
                volume_sma_value=opp.evidence.volume_sma_value,
                breakout_volume=opp.evidence.breakout_volume,
                retest_low=opp.evidence.retest_low,
                confirmation_volume=opp.evidence.confirmation_volume,
                decision=opp.evidence.decision,
            ),
        )
        for opp in result.opportunities
    ]

    return OpportunityScanResponse(
        universe_name=snapshot.name,
        universe_version=snapshot.version,
        timeframe=payload.timeframe,
        start=payload.start,
        end=payload.end,
        symbols_scanned=result.symbols_scanned,
        eligible_count=result.eligible_count,
        no_setup_count=result.symbols_scanned - result.eligible_count,
        opportunities=opportunities,
    )
