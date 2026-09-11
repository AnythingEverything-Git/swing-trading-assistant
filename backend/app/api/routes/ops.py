"""Ops endpoints: live scheduler dashboard status + host heartbeats."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_product_status_service
from app.api.schemas import (
    ReadinessGateResponse,
    ReadinessResponse,
    SchedulerEnableRequest,
    SchedulerHeartbeatRequest,
    SchedulerHeartbeatResponse,
    SchedulerJobResponse,
    SchedulerRunAcceptedResponse,
    SchedulerRunRequest,
    SchedulerStatusResponse,
)
from app.application.ops.readiness import evaluate_readiness
from app.application.ops.scheduler_control import start_job_manual
from app.application.ops.scheduler_status import (
    KNOWN_JOB_IDS,
    apply_heartbeat,
    ensure_registry,
    seed_registry_from_settings,
    set_job_enabled,
    snapshot_jobs,
)
from app.application.product.status_service import ProductStatusService
from app.core.config import get_settings
from app.infrastructure.market_data.source import live_ready, normalize_market_data_source

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


def _job_response(raw: dict) -> SchedulerJobResponse:
    return SchedulerJobResponse(**raw)


def _status_payload(request: Request, product) -> SchedulerStatusResponse:
    settings = get_settings()
    token = getattr(settings, "upstox_access_token", None)
    return SchedulerStatusResponse(
        environment=product.environment,
        data_source=normalize_market_data_source(settings.market_data_source),
        live_ready=live_ready(settings),
        upstox_token_configured=bool(token and str(token).strip()),
        refresh_mutex_held=bool(getattr(request.app.state, "refresh_running", False)),
        history_backfill_running=bool(getattr(request.app.state, "history_backfill_running", False)),
        last_candle_time=product.last_candle_time,
        last_1m_candle_time=product.last_1m_candle_time,
        symbols_with_candles=product.symbols_with_candles,
        symbols_with_1m=product.symbols_with_1m,
        stale_risk=product.stale_risk,
        jobs=[_job_response(item) for item in snapshot_jobs(request.app.state)],
    )


@router.get("/schedulers", response_model=SchedulerStatusResponse)
async def list_schedulers(
    request: Request,
    svc: ProductStatusService = Depends(get_product_status_service),
) -> SchedulerStatusResponse:
    settings = get_settings()
    seed_registry_from_settings(request.app.state, settings)
    ensure_registry(request.app.state)
    product = await svc.status()
    return _status_payload(request, product)


@router.get("/schedulers/{job_id}", response_model=SchedulerJobResponse)
async def get_scheduler_job(job_id: str, request: Request) -> SchedulerJobResponse:
    job_id = (job_id or "").strip()
    if job_id not in KNOWN_JOB_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    seed_registry_from_settings(request.app.state, get_settings())
    reg = ensure_registry(request.app.state)
    return _job_response(reg[job_id].to_dict())


@router.patch("/schedulers/{job_id}", response_model=SchedulerJobResponse)
async def patch_scheduler_job(
    job_id: str,
    payload: SchedulerEnableRequest,
    request: Request,
) -> SchedulerJobResponse:
    job_id = (job_id or "").strip()
    if job_id not in KNOWN_JOB_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    seed_registry_from_settings(request.app.state, get_settings())
    job = set_job_enabled(request.app.state, job_id, bool(payload.enabled))
    return _job_response(job.to_dict())


@router.post("/schedulers/{job_id}/run", response_model=SchedulerRunAcceptedResponse, status_code=202)
async def run_scheduler_job(
    job_id: str,
    request: Request,
    payload: SchedulerRunRequest | None = None,
) -> SchedulerRunAcceptedResponse:
    job_id = (job_id or "").strip()
    if job_id not in KNOWN_JOB_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    seed_registry_from_settings(request.app.state, get_settings())
    body = payload or SchedulerRunRequest()
    try:
        accepted = start_job_manual(
            request.app,
            job_id,
            universe=body.universe,
            stage=body.stage,
            start=body.start,
            end=body.end,
            lookback_days=body.lookback_days,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    reg = ensure_registry(request.app.state)
    return SchedulerRunAcceptedResponse(
        accepted=True,
        job_id=job_id,
        status="running",
        job=_job_response(reg[job_id].to_dict()),
        universe=accepted.get("universe"),
        start=accepted.get("start"),
        end=accepted.get("end"),
    )


@router.get("/readiness", response_model=ReadinessResponse)
async def get_readiness(
    request: Request,
    universe: str = Query(default="NIFTY_500"),
    session: AsyncSession = Depends(get_db),
) -> ReadinessResponse:
    """Desk readiness SLOs (provider-max aware) for Nifty 500 keep-alive."""
    since = getattr(request.app.state, "refresh_running_since", None)
    if isinstance(since, datetime):
        running_since = since
    else:
        running_since = None
    report = await evaluate_readiness(
        session,
        universe=universe,
        settings=get_settings(),
        refresh_mutex_held=bool(getattr(request.app.state, "refresh_running", False)),
        refresh_running_since=running_since,
        history_backfill_running=bool(getattr(request.app.state, "history_backfill_running", False)),
    )
    return ReadinessResponse(
        universe=report.universe,
        ready=report.ready,
        status=report.status,
        as_of=report.as_of,
        provider_1d_max=report.provider_1d_max,
        calendar_1d_expected=report.calendar_1d_expected,
        gates=[ReadinessGateResponse(**g.to_dict()) for g in report.gates],
        recommendations=list(report.recommendations),
    )


@router.post("/schedulers/heartbeat", response_model=SchedulerHeartbeatResponse)
async def scheduler_heartbeat(
    payload: SchedulerHeartbeatRequest,
    request: Request,
) -> SchedulerHeartbeatResponse:
    job_id = (payload.job_id or "").strip()
    if job_id not in KNOWN_JOB_IDS:
        raise HTTPException(status_code=400, detail=f"Unknown job_id: {job_id}")
    status = (payload.status or "").strip().lower()
    if status not in ("ok", "failed", "skipped", "unknown", "running"):
        raise HTTPException(
            status_code=400,
            detail="status must be one of: ok, failed, skipped, unknown, running",
        )
    ensure_registry(request.app.state)
    job = apply_heartbeat(
        request.app.state,
        job_id=job_id,
        status=status,
        detail=payload.detail,
        phase=payload.phase,
        running=payload.running,
    )
    return SchedulerHeartbeatResponse(ok=True, job=_job_response(job.to_dict()))
