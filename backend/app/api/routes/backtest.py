from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_backtest_service
from app.api.schemas import BacktestRequest, BacktestResponse, BacktestTradeResponse, PerformanceMetricsResponse
from app.application.backtesting.backtest_service import BacktestService
from app.application.narrative.backtest_interpreter import interpret_backtest, metrics_as_dict
from app.application.narrative.grounded_narrator import GroundedNarrator, narrative_llm_enabled
from app.core.config import get_settings
import httpx


router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    payload: BacktestRequest,
    svc: BacktestService = Depends(get_backtest_service),
) -> BacktestResponse:
    if payload.start > payload.end:
        raise HTTPException(status_code=400, detail="start must be <= end")

    try:
        result = await svc.run(
            payload.symbol,
            payload.timeframe,
            payload.start,
            payload.end,
            payload.account_equity,
            payload.risk_percent,
            slippage_per_share=payload.slippage_per_share,
            cost_per_trade=payload.cost_per_trade,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    trades = [
        BacktestTradeResponse(
            symbol=trade.symbol,
            timeframe=trade.timeframe,
            direction=trade.direction,
            setup_time=trade.setup_time,
            entry_time=trade.entry_time,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            target=trade.target,
            exit_time=trade.exit_time,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            risk_per_share=trade.risk_per_share,
            risk_amount=trade.risk_per_share * trade.quantity,
            pnl=trade.pnl_per_share * trade.quantity,
            exit_reason=trade.exit_reason.value,
        )
        for trade in result.trades
    ]
    metrics_payload = metrics_as_dict(result.metrics)
    settings = get_settings()
    if narrative_llm_enabled(settings):
        async with httpx.AsyncClient(timeout=20.0) as client:
            interp = await interpret_backtest(
                GroundedNarrator(client, settings),
                metrics=metrics_payload,
                symbol=result.symbol,
            )
    else:
        interp = await interpret_backtest(None, metrics=metrics_payload, symbol=result.symbol)

    return BacktestResponse(
        symbol=result.symbol,
        timeframe=result.timeframe,
        completed_trades=len(trades),
        trades=trades,
        metrics=PerformanceMetricsResponse(
            total_trades=result.metrics.total_trades,
            winning_trades=result.metrics.winning_trades,
            losing_trades=result.metrics.losing_trades,
            win_rate=result.metrics.win_rate,
            total_pnl=result.metrics.total_pnl,
            average_pnl=result.metrics.average_pnl,
            total_r=result.metrics.total_r,
            average_r=result.metrics.average_r,
            maximum_drawdown=result.metrics.maximum_drawdown,
        ),
        interpretation=interp.text,
        interpretation_provider=interp.provider,
    )