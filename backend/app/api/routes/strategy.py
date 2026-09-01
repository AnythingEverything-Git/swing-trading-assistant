from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_strategy_evaluation_service
from app.api.schemas import StrategyEvaluationRequest, StrategyEvaluationResponse
from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


@router.post("/evaluate", response_model=StrategyEvaluationResponse)
async def evaluate_strategy(
    payload: StrategyEvaluationRequest,
    svc: StrategyEvaluationService = Depends(get_strategy_evaluation_service),
) -> StrategyEvaluationResponse:
    if payload.start > payload.end:
        raise HTTPException(status_code=400, detail="start must be <= end")

    try:
        result = await svc.evaluate(payload.symbol, payload.timeframe, payload.start, payload.end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.candidate is None and result.evidence is None:
        return StrategyEvaluationResponse(
            has_setup=result.has_setup,
            candidate=None,
            evidence=None,
            status=result.status,
            reason=result.reason,
        )

    candidate = None if result.candidate is None else {
        "symbol": result.candidate.symbol,
        "timeframe": result.candidate.timeframe,
        "direction": result.candidate.direction,
        "entry_price": result.candidate.entry_price,
        "stop_loss": result.candidate.stop_loss,
        "target": result.candidate.target,
        "risk_per_share": result.candidate.risk_per_share,
        "reward": result.candidate.reward,
        "risk_reward_ratio": result.candidate.risk_reward_ratio,
        "setup_name": result.candidate.setup_name,
    }

    evidence = None if result.evidence is None else {
        "resistance": result.evidence.resistance,
        "breakout_candle_index": result.evidence.breakout_candle_index,
        "breakout_candle_time": result.evidence.breakout_candle_time,
        "retest_candle_index": result.evidence.retest_candle_index,
        "retest_candle_time": result.evidence.retest_candle_time,
        "confirmation_candle_index": result.evidence.confirmation_candle_index,
        "confirmation_candle_time": result.evidence.confirmation_candle_time,
        "atr_value": result.evidence.atr_value,
        "volume_sma_value": result.evidence.volume_sma_value,
        "breakout_volume": result.evidence.breakout_volume,
        "retest_low": result.evidence.retest_low,
        "confirmation_volume": result.evidence.confirmation_volume,
        "decision": result.evidence.decision,
    }

    return StrategyEvaluationResponse(
        has_setup=result.has_setup,
        candidate=candidate,
        evidence=evidence,
        status=result.status,
        reason=result.reason,
    )
