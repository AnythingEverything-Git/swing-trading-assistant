"""Paper trading API — simulated fills only; never places broker orders."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_ingest_provider
from app.api.schemas import (
    PaperCloseRequest,
    PaperSummaryResponse,
    PaperTickResponse,
    PaperTradeListResponse,
    PaperTradeResponse,
)
from app.application.paper import PaperTradeService
from app.domain.paper import PaperTrade
from app.infrastructure.database.repositories.paper_trade_repository import PaperTradeRepository

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])

_CLAIM = "PRACTICE TRADES ONLY — fake money, no real broker orders"


def _trade_response(trade: PaperTrade) -> PaperTradeResponse:
    assert trade.id is not None
    return PaperTradeResponse(
        id=trade.id,
        scan_run_id=trade.scan_run_id,
        symbol=trade.symbol,
        direction=trade.direction,
        entry_price=trade.entry_price,
        stop_loss=trade.stop_loss,
        target=trade.target,
        quantity=trade.quantity,
        risk_amount=trade.risk_amount,
        status=trade.status,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
        exit_price=trade.exit_price,
        exit_reason=trade.exit_reason,
        last_mark_price=trade.last_mark_price,
        unrealized_pnl=trade.unrealized_pnl,
        realized_pnl=trade.realized_pnl,
        setup_name=trade.setup_name,
        quality_score=trade.quality_score,
        updated_at=trade.updated_at,
        claim="PRACTICE — fake money, no real broker orders",
    )


def get_paper_service(
    session: AsyncSession = Depends(get_db),
    provider=Depends(get_ingest_provider),
) -> PaperTradeService:
    return PaperTradeService(PaperTradeRepository(session), quote_provider=provider)


@router.get("/trades", response_model=PaperTradeListResponse)
async def list_paper_trades(
    status: str = Query(default="ALL", pattern="^(PENDING|OPEN|CLOSED|ACTIVE|ALL)$"),
    svc: PaperTradeService = Depends(get_paper_service),
) -> PaperTradeListResponse:
    trades = await svc.list_trades(status)
    summary = await svc.summary()
    return PaperTradeListResponse(
        claim=_CLAIM,
        trades=[_trade_response(t) for t in trades],
        pending_count=summary.pending_count,
        open_count=summary.open_count,
        closed_count=summary.closed_count,
        total_unrealized=summary.total_unrealized,
        total_realized=summary.total_realized,
    )


@router.post("/tick", response_model=PaperTickResponse)
async def tick_paper_trades(
    svc: PaperTradeService = Depends(get_paper_service),
) -> PaperTickResponse:
    result = await svc.tick()
    total_unrealized = sum(
        (t.unrealized_pnl or Decimal("0") for t in result.open_trades),
        Decimal("0"),
    )
    return PaperTickResponse(
        claim=_CLAIM,
        marks_applied=result.marks_applied,
        filled_this_tick=[_trade_response(t) for t in result.filled_this_tick],
        closed_this_tick=[_trade_response(t) for t in result.closed_this_tick],
        pending_trades=[_trade_response(t) for t in result.pending_trades],
        open_trades=[_trade_response(t) for t in result.open_trades],
        total_unrealized=total_unrealized,
    )


@router.post("/trades/{trade_id}/close", response_model=PaperTradeResponse)
async def close_paper_trade(
    trade_id: int,
    payload: PaperCloseRequest | None = None,
    svc: PaperTradeService = Depends(get_paper_service),
) -> PaperTradeResponse:
    try:
        price = payload.price if payload is not None else None
        trade = await svc.close_manual(trade_id, price=price)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _trade_response(trade)


@router.get("/summary", response_model=PaperSummaryResponse)
async def paper_summary(
    svc: PaperTradeService = Depends(get_paper_service),
) -> PaperSummaryResponse:
    summary = await svc.summary()
    return PaperSummaryResponse(
        claim=summary.claim,
        pending_count=summary.pending_count,
        open_count=summary.open_count,
        closed_count=summary.closed_count,
        total_unrealized=summary.total_unrealized,
        total_realized=summary.total_realized,
        winning_closed=summary.winning_closed,
        losing_closed=summary.losing_closed,
    )
