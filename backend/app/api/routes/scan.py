"""Thin FastAPI surface for Nifty opportunity scans over persisted candles."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_universe_scan_report_service, get_product_status_service
from app.application.alerts.composer import compose_scan_alert
from app.application.alerts.brief_builder import build_scan_brief
from app.application.narrative.grounded_narrator import GroundedNarrator, narrative_llm_enabled
from app.application.paper import PaperTradeService
from app.application.product.status_service import ProductStatusService
from app.application.scan.scan_ai_enrichment import enrich_presented_scan
from app.application.scan.scan_job_queue import get_or_create_scan_queue
from app.application.scan.scan_presentation import present_scan
from app.application.scan.book_constructor import build_personal_book, explain_personal_book
from app.application.scan.scan_response_builder import (
    enrich_current_prices_with_provider,
    to_scan_response,
)
from app.core.config import get_settings
from app.api.schemas import (
    OpportunityScanRequest,
    OpportunityScanResponse,
    PersonalBookRequest,
    PersonalBookResponse,
    PersonalBookPickResponse,
    PersonalBookRejectionResponse,
    ScanJobAcceptedResponse,
    ScanRunStatusResponse,
    ScanRunSummaryResponse,
)
import httpx
from app.application.scan.universe_scan_report_service import UniverseScanReportService
from app.domain.entities.scan_run import (
    SCAN_STATUS_COMPLETED,
    SCAN_STATUS_FAILED,
    SCAN_STATUS_QUEUED,
    SCAN_STATUS_RUNNING,
)
from app.infrastructure.database.repositories.paper_trade_repository import PaperTradeRepository
from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository
from app.infrastructure.universe import get_universe
from app.infrastructure.universe.static_file_universe import SUPPORTED_UNIVERSE_NAMES

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])

_SUPPORTED_TIMEFRAMES = frozenset({"1d"})
_PAPER_CLAIM = "PRACTICE TRADES ONLY — fake money, no real broker orders"

# Re-export for scripts that imported builders from this module.
__all__ = ["router", "to_scan_response", "enrich_current_prices_with_provider"]


def _job_parameters(payload: OpportunityScanRequest, *, universe_name: str, universe_version: str) -> dict:
    return {
        "universe_name": universe_name,
        "universe_version": universe_version,
        "timeframe": payload.timeframe,
        "start": payload.start.isoformat(),
        "end": payload.end.isoformat(),
        "top_n": payload.top_n,
        "min_score": str(payload.min_score) if payload.min_score is not None else None,
        "account_equity": str(payload.account_equity) if payload.account_equity is not None else None,
        "risk_percent": str(payload.risk_percent),
        "enable_paper_trading": payload.enable_paper_trading,
    }


@router.post(
    "/opportunities",
    response_model=None,
    responses={
        200: {"model": OpportunityScanResponse},
        202: {"model": ScanJobAcceptedResponse},
    },
)
async def scan_opportunities(
    payload: OpportunityScanRequest,
    request: Request,
    sync: bool = Query(default=False, description="Run inline (tests/scripts). Default queues a job."),
    svc: UniverseScanReportService = Depends(get_universe_scan_report_service),
    session: AsyncSession = Depends(get_db),
    product: ProductStatusService = Depends(get_product_status_service),
):
    if payload.start > payload.end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if payload.timeframe not in _SUPPORTED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="timeframe must be '1d'")

    try:
        universe = get_universe(payload.universe)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"universe must be one of: {', '.join(SUPPORTED_UNIVERSE_NAMES)}",
        ) from exc

    snapshot = universe.get_snapshot()
    started_at = datetime.now(timezone.utc)
    parameters = _job_parameters(
        payload, universe_name=snapshot.name, universe_version=snapshot.version
    )

    if not sync:
        scan_run = await ScanRunRepository(session).create(
            started_at=started_at,
            finished_at=None,
            universe_date=payload.end,
            universe_version=snapshot.version,
            parameters=parameters,
            result_count=0,
            metadata=None,
            result_payload=None,
            status=SCAN_STATUS_QUEUED,
        )
        # Commit before enqueue so the worker session can see the row.
        await session.commit()
        queue = get_or_create_scan_queue(request.app)
        queue.ensure_worker(request.app)
        queue.enqueue(scan_run.id)
        return JSONResponse(
            status_code=202,
            content=ScanJobAcceptedResponse(
                scan_run_id=scan_run.id, status=SCAN_STATUS_QUEUED
            ).model_dump(),
        )

    # sync=1: inline evaluation for tests and scripts (same shape as before).
    try:
        result = await svc.scan_universe(universe, payload.timeframe, payload.start, payload.end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    presented = present_scan(
        result,
        account_equity=payload.account_equity,
        risk_percent=payload.risk_percent if payload.account_equity is not None else None,
        top_n=payload.top_n,
        min_score=payload.min_score,
    )
    settings = get_settings()
    presented, dq_bullets, _provider = await enrich_presented_scan(presented, settings=settings)
    from app.infrastructure.market_data.source import data_claim as _data_claim

    claim_text = _data_claim(settings)
    if narrative_llm_enabled(settings):
        async with httpx.AsyncClient(timeout=30.0) as client:
            brief = await build_scan_brief(
                GroundedNarrator(client, settings),
                presented,
                mode="premarket",
                data_claim=claim_text,
            )
            ai_brief = brief.text
    else:
        brief = await build_scan_brief(
            None, presented, mode="premarket", data_claim=claim_text
        )
        ai_brief = brief.text

    last_candle_time = None
    try:
        status = await product.status(payload.timeframe)
        last_candle_time = status.last_candle_time
    except Exception:
        last_candle_time = None

    finished_at = datetime.now(timezone.utc)
    response = to_scan_response(
        presented=presented,
        universe_name=snapshot.name,
        universe_version=snapshot.version,
        timeframe=payload.timeframe,
        start=payload.start,
        end=payload.end,
        scan_run_id=None,
        last_candle_time=last_candle_time,
        data_quality_bullets=dq_bullets,
        ai_brief=ai_brief,
    )
    provider = getattr(request.app.state, "upstox_provider", None)
    await enrich_current_prices_with_provider(response, provider)

    scan_run = await ScanRunRepository(session).create(
        started_at=started_at,
        finished_at=finished_at,
        universe_date=payload.end,
        universe_version=snapshot.version,
        parameters={**parameters, "data_source": response.data_source},
        result_count=result.eligible_count,
        metadata={
            "symbols_scanned": result.symbols_scanned,
            "eligible_count": result.eligible_count,
            "forming_count": result.forming_count,
            "no_setup_count": result.no_setup_count,
            "unavailable_count": result.unavailable_count,
            "error_count": result.error_count,
            "issues_recorded": len(result.issues),
            "data_source": response.data_source,
        },
        result_payload=response.model_dump(mode="json"),
        status=SCAN_STATUS_COMPLETED,
    )
    response.scan_run_id = scan_run.id
    response.status = SCAN_STATUS_COMPLETED
    alert = compose_scan_alert(
        presented,
        universe_name=snapshot.name,
        data_claim=response.data_claim,
        scan_run_id=scan_run.id,
        frontend_base_url=settings.frontend_base_url,
        ai_brief=ai_brief,
        data_quality_bullets=dq_bullets,
    )
    response.alert_preview = alert.body

    if payload.enable_paper_trading:
        try:
            ingest = getattr(request.app.state, "ingest_provider", None)
            paper_svc = PaperTradeService(PaperTradeRepository(session), quote_provider=ingest)
            paper_result = await paper_svc.open_from_scan(response)
            response.paper_opened_count = paper_result.opened
            response.paper_skipped_count = paper_result.skipped_qty + paper_result.skipped_open
            response.paper_claim = _PAPER_CLAIM
        except Exception:
            response.paper_opened_count = 0
            response.paper_skipped_count = 0
            response.paper_claim = _PAPER_CLAIM
    else:
        response.paper_opened_count = 0
        response.paper_skipped_count = 0
        response.paper_claim = None

    return response


@router.post("/book", response_model=PersonalBookResponse)
async def build_scan_book(
    payload: PersonalBookRequest,
    session: AsyncSession = Depends(get_db),
) -> PersonalBookResponse:
    """Rules-based 'take these N' book. LLM only explains after the solver."""
    from decimal import Decimal

    from app.application.scan.opportunity_scan_service import EligibleOpportunity
    from app.application.scan.quality_score import QualityScore
    from app.application.scan.scan_presentation import PresentedOpportunity
    from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate

    opportunities_raw: list[dict] = []
    if payload.scan_run_id is not None:
        run = await ScanRunRepository(session).get_by_id(payload.scan_run_id)
        if run is None or not run.result_payload:
            raise HTTPException(status_code=404, detail="scan run not found")
        body = run.result_payload
        opportunities_raw = list(body.get("opportunities") or body.get("top") or [])
    elif payload.opportunities:
        opportunities_raw = [item.model_dump(mode="json") for item in payload.opportunities]
    else:
        raise HTTPException(status_code=400, detail="scan_run_id or opportunities required")

    presented_items: list[PresentedOpportunity] = []

    def _as_dt(value):
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    for idx, item in enumerate(opportunities_raw, start=1):
        try:
            cand = item.get("candidate") or {}
            evid = item.get("evidence") or {}
            candidate = TradeCandidate(
                symbol=str(cand.get("symbol") or item.get("symbol")),
                timeframe=str(cand.get("timeframe") or "1d"),
                direction=str(cand.get("direction") or "LONG"),
                entry_price=Decimal(str(cand["entry_price"])),
                stop_loss=Decimal(str(cand["stop_loss"])),
                target=Decimal(str(cand["target"])),
                risk_per_share=Decimal(str(cand.get("risk_per_share") or "1")),
                reward=Decimal(str(cand.get("reward") or "1")),
                risk_reward_ratio=Decimal(str(cand.get("risk_reward_ratio") or "1")),
                setup_name=str(cand.get("setup_name") or "breakout_retest"),
            )
            evidence = StrategyEvidence(
                resistance=Decimal(str(evid.get("resistance") or evid.get("structure_level"))),
                breakout_candle_index=int(evid["breakout_candle_index"]),
                breakout_candle_time=_as_dt(evid["breakout_candle_time"]),
                retest_candle_index=int(evid["retest_candle_index"]),
                retest_candle_time=_as_dt(evid["retest_candle_time"]),
                confirmation_candle_index=int(evid["confirmation_candle_index"]),
                confirmation_candle_time=_as_dt(evid["confirmation_candle_time"]),
                atr_value=Decimal(str(evid["atr_value"])),
                volume_sma_value=Decimal(str(evid["volume_sma_value"])),
                breakout_volume=evid.get("breakout_volume"),
                retest_low=Decimal(str(evid.get("retest_low") or evid.get("retest_extreme"))),
                confirmation_volume=evid.get("confirmation_volume"),
                decision=str(evid.get("decision") or "ELIGIBLE"),
                direction=str(evid.get("direction") or candidate.direction),
            )
            quality = QualityScore(
                score=Decimal(str(item.get("quality_score") or "0")),
                volume_thrust=Decimal(str(item.get("volume_thrust") or "1")),
                confirmation_volume_ratio=Decimal(str(item.get("confirmation_volume_ratio") or "1")),
                retest_tightness=Decimal(str(item.get("retest_tightness") or "1")),
                risk_percent=Decimal(str(item.get("risk_percent") or "0")),
                reason=str(item.get("quality_reason") or ""),
            )
            presented_items.append(
                PresentedOpportunity(
                    opportunity=EligibleOpportunity(
                        symbol=candidate.symbol,
                        candidate=candidate,
                        evidence=evidence,
                    ),
                    quality=quality,
                    rank=int(item.get("rank") or idx),
                    narrative=str(item.get("narrative") or ""),
                    invalidation=str(item.get("invalidation") or ""),
                    quantity=item.get("quantity"),
                    risk_amount=Decimal(str(item["risk_amount"])) if item.get("risk_amount") is not None else None,
                )
            )
        except Exception:
            continue

    presented_items.sort(key=lambda x: x.rank)
    open_symbols = await PaperTradeRepository(session).list_open_symbols()
    book = build_personal_book(
        presented_items,
        account_equity=payload.account_equity,
        risk_percent=payload.risk_percent,
        max_positions=payload.max_positions,
        open_symbols=open_symbols,
    )
    settings = get_settings()
    if narrative_llm_enabled(settings):
        async with httpx.AsyncClient(timeout=25.0) as client:
            book = await explain_personal_book(GroundedNarrator(client, settings), book)
    else:
        book = await explain_personal_book(None, book)

    return PersonalBookResponse(
        picks=[
            PersonalBookPickResponse(
                symbol=p.symbol,
                direction=p.direction,
                rank=p.rank,
                quality_score=p.quality_score,
                quantity=p.quantity,
                risk_amount=p.risk_amount,
                entry=p.entry,
                stop=p.stop,
                target=p.target,
                risk_reward_ratio=p.risk_reward_ratio,
            )
            for p in book.picks
        ],
        rejected=[PersonalBookRejectionResponse(symbol=r.symbol, reason=r.reason) for r in book.rejected],
        rationale_rules=list(book.rationale_rules),
        explanation=book.explanation,
        explanation_provider=book.explanation_provider,
    )


@router.get("/runs", response_model=list[ScanRunSummaryResponse])
async def list_scan_runs(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[ScanRunSummaryResponse]:
    runs = await ScanRunRepository(session).list_recent(limit=limit)
    summaries: list[ScanRunSummaryResponse] = []
    for run in runs:
        parameters = run.parameters or {}
        metadata = run.metadata or {}
        summaries.append(
            ScanRunSummaryResponse(
                id=run.id,
                started_at=run.started_at,
                finished_at=run.finished_at,
                universe_name=parameters.get("universe_name"),
                universe_version=run.universe_version,
                result_count=run.result_count,
                symbols_scanned=metadata.get("symbols_scanned"),
                data_source=parameters.get("data_source") or metadata.get("data_source"),
                status=run.status,
            )
        )
    return summaries


@router.get("/runs/{scan_run_id}", response_model=None)
async def get_scan_run(
    scan_run_id: int,
    session: AsyncSession = Depends(get_db),
):
    run = await ScanRunRepository(session).get_by_id(scan_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="scan run not found")

    if run.status in {SCAN_STATUS_QUEUED, SCAN_STATUS_RUNNING}:
        return ScanRunStatusResponse(
            scan_run_id=run.id,
            status=run.status,
            error_message=None,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    if run.status == SCAN_STATUS_FAILED:
        return ScanRunStatusResponse(
            scan_run_id=run.id,
            status=run.status,
            error_message=run.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    if not run.result_payload:
        raise HTTPException(status_code=404, detail="scan run not found")

    payload = dict(run.result_payload)
    payload["scan_run_id"] = run.id
    payload["status"] = run.status or SCAN_STATUS_COMPLETED
    return OpportunityScanResponse.model_validate(payload)
