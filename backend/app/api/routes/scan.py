"""Thin FastAPI surface for Nifty opportunity scans over persisted candles."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_universe_scan_report_service, get_product_status_service
from app.api.schemas import (
    EligibleOpportunityResponse,
    FormingSetupResponse,
    OpportunityScanRequest,
    OpportunityScanResponse,
    ScanIssueResponse,
    ScanRunSummaryResponse,
    StrategyCandidateResponse,
    StrategyEvidenceResponse,
)
from app.application.alerts.composer import compose_scan_alert
from app.application.product.status_service import ProductStatusService
from app.application.scan.scan_presentation import PresentedOpportunity, PresentedScan, present_scan
from app.application.scan.universe_scan_report_service import UniverseScanReportService
from app.core.config import get_settings
from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository
from app.infrastructure.market_data.source import data_claim, normalize_market_data_source
from app.infrastructure.universe import get_universe
from app.infrastructure.universe.static_file_universe import SUPPORTED_UNIVERSE_NAMES

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])

_SUPPORTED_TIMEFRAMES = frozenset({"1d"})


def _candidate_response(candidate) -> StrategyCandidateResponse:
    return StrategyCandidateResponse(
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        direction=candidate.direction,
        entry_price=candidate.entry_price,
        stop_loss=candidate.stop_loss,
        target=candidate.target,
        risk_per_share=candidate.risk_per_share,
        reward=candidate.reward,
        risk_reward_ratio=candidate.risk_reward_ratio,
        setup_name=candidate.setup_name,
    )


def _evidence_response(evidence) -> StrategyEvidenceResponse:
    return StrategyEvidenceResponse(
        resistance=evidence.resistance,
        breakout_candle_index=evidence.breakout_candle_index,
        breakout_candle_time=evidence.breakout_candle_time,
        retest_candle_index=evidence.retest_candle_index,
        retest_candle_time=evidence.retest_candle_time,
        confirmation_candle_index=evidence.confirmation_candle_index,
        confirmation_candle_time=evidence.confirmation_candle_time,
        atr_value=evidence.atr_value,
        volume_sma_value=evidence.volume_sma_value,
        breakout_volume=evidence.breakout_volume,
        retest_low=evidence.retest_low,
        confirmation_volume=evidence.confirmation_volume,
        decision=evidence.decision,
    )


def _opportunity_response(item: PresentedOpportunity) -> EligibleOpportunityResponse:
    opp = item.opportunity
    return EligibleOpportunityResponse(
        symbol=opp.symbol,
        candidate=_candidate_response(opp.candidate),
        evidence=_evidence_response(opp.evidence),
        quality_score=item.quality.score,
        rank=item.rank,
        quantity=item.quantity,
        risk_amount=item.risk_amount,
        narrative=item.narrative,
        invalidation=item.invalidation,
        quality_reason=item.quality.reason,
    )


def _forming_response(item) -> FormingSetupResponse:
    forming = item.forming
    return FormingSetupResponse(
        symbol=forming.symbol,
        timeframe=forming.timeframe,
        stage=forming.stage,
        resistance=forming.resistance,
        breakout_candle_index=forming.breakout_candle_index,
        breakout_candle_time=forming.breakout_candle_time,
        breakout_volume=forming.breakout_volume,
        atr_value=forming.atr_value,
        volume_sma_value=forming.volume_sma_value,
        bars_elapsed=forming.bars_elapsed,
        bars_remaining=forming.bars_remaining,
        reason=forming.reason,
        narrative=item.narrative,
        retest_candle_index=forming.retest_candle_index,
        retest_candle_time=forming.retest_candle_time,
        retest_low=forming.retest_low,
    )


def to_scan_response(
    *,
    presented: PresentedScan,
    universe_name: str,
    universe_version: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    scan_run_id: int | None,
    last_candle_time: datetime | None,
) -> OpportunityScanResponse:
    settings = get_settings()
    source = normalize_market_data_source(settings.market_data_source)
    claim = data_claim(settings)
    opportunities = [_opportunity_response(item) for item in presented.opportunities]
    top = [_opportunity_response(item) for item in presented.top]
    forming = [_forming_response(item) for item in presented.forming]
    issues = [
        ScanIssueResponse(symbol=item.symbol, status=item.status, detail=item.detail)
        for item in presented.report.issues
    ]
    alert = compose_scan_alert(presented, universe_name=universe_name, data_claim=claim)
    return OpportunityScanResponse(
        universe_name=universe_name,
        universe_version=universe_version,
        timeframe=timeframe,
        start=start,
        end=end,
        symbols_scanned=presented.report.symbols_scanned,
        eligible_count=presented.report.eligible_count,
        no_setup_count=presented.report.no_setup_count,
        unavailable_count=presented.report.unavailable_count,
        error_count=presented.report.error_count,
        opportunities=opportunities,
        issues=issues,
        scan_run_id=scan_run_id,
        forming_count=presented.report.forming_count,
        forming=forming,
        top=top,
        data_source=source,
        data_claim=claim,
        last_candle_time=last_candle_time,
        alert_preview=alert.body,
    )


async def enrich_current_prices(response: OpportunityScanResponse, request: Request) -> None:
    provider = getattr(request.app.state, "upstox_provider", None)
    quote_fn = getattr(provider, "get_last_traded_prices", None)
    if quote_fn is None:
        return
    symbols = [item.symbol for item in response.opportunities]
    symbols.extend(item.symbol for item in response.forming)
    if not symbols:
        return
    try:
        quotes = await quote_fn(symbols)
    except Exception:
        return

    def apply_price(symbol: str, target) -> None:
        payload = quotes.get(symbol)
        if payload is None:
            return
        last_price = payload.get("last_price")
        target.current_price = Decimal(str(last_price)) if last_price is not None else None
        try:
            raw = payload.get("raw", {}) or {}
            net_change = raw.get("net_change")
            if net_change is not None and target.current_price is not None:
                net_change_decimal = Decimal(str(net_change))
                prev_close = target.current_price - net_change_decimal
                if prev_close != 0:
                    target.current_price_change_percent = (net_change_decimal / prev_close) * Decimal("100")
        except Exception:
            target.current_price_change_percent = None

    for item in response.opportunities:
        apply_price(item.symbol, item)
    for item in response.top:
        apply_price(item.symbol, item)
    for item in response.forming:
        apply_price(item.symbol, item)


@router.post("/opportunities", response_model=OpportunityScanResponse)
async def scan_opportunities(
    payload: OpportunityScanRequest,
    request: Request,
    svc: UniverseScanReportService = Depends(get_universe_scan_report_service),
    session: AsyncSession = Depends(get_db),
    product: ProductStatusService = Depends(get_product_status_service),
) -> OpportunityScanResponse:
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
    )
    await enrich_current_prices(response, request)

    scan_run = await ScanRunRepository(session).create(
        started_at=started_at,
        finished_at=finished_at,
        universe_date=payload.end,
        universe_version=snapshot.version,
        parameters={
            "universe_name": snapshot.name,
            "timeframe": payload.timeframe,
            "start": payload.start.isoformat(),
            "end": payload.end.isoformat(),
            "top_n": payload.top_n,
            "data_source": response.data_source,
        },
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
    )
    response.scan_run_id = scan_run.id
    return response


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
            )
        )
    return summaries


@router.get("/runs/{scan_run_id}", response_model=OpportunityScanResponse)
async def get_scan_run(
    scan_run_id: int,
    session: AsyncSession = Depends(get_db),
) -> OpportunityScanResponse:
    run = await ScanRunRepository(session).get_by_id(scan_run_id)
    if run is None or not run.result_payload:
        raise HTTPException(status_code=404, detail="scan run not found")
    payload = dict(run.result_payload)
    payload["scan_run_id"] = run.id
    return OpportunityScanResponse.model_validate(payload)
