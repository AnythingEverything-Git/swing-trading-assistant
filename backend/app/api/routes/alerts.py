"""Alert delivery API — SES/SMTP brief send from Brief center."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.application.alerts.brief_send import send_brief_email
from app.application.alerts.email_delivery import resolve_smtp_target
from app.core.config import get_settings
from app.domain.entities.scan_run import SCAN_STATUS_COMPLETED
from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class SendBriefRequest(BaseModel):
    mode: str = Field(default="morning", description="morning | eod")
    scan_run_id: int | None = None


class SendBriefResponse(BaseModel):
    email_sent: bool
    detail: str
    subject: str | None = None
    recipients: list[str] = []
    scan_run_id: int | None = None
    provider: str | None = None


class AlertConfigStatusResponse(BaseModel):
    configured: bool
    provider: str | None = None
    detail: str
    from_email: str | None = None
    recipient_count: int = 0


@router.get("/status", response_model=AlertConfigStatusResponse)
async def alert_config_status() -> AlertConfigStatusResponse:
    settings = get_settings()
    target = resolve_smtp_target(settings)
    if isinstance(target, str):
        return AlertConfigStatusResponse(
            configured=False,
            provider=(settings.email_provider or "ses").strip().lower(),
            detail=target,
        )
    return AlertConfigStatusResponse(
        configured=True,
        provider=target.provider,
        detail=f"Ready via {target.provider} ({target.host})",
        from_email=target.from_addr,
        recipient_count=len(target.recipients),
    )


@router.post("/brief/send", response_model=SendBriefResponse)
async def send_brief(
    payload: SendBriefRequest,
    session: AsyncSession = Depends(get_db),
) -> SendBriefResponse:
    mode = (payload.mode or "morning").strip().lower()
    if mode not in {"morning", "eod"}:
        raise HTTPException(status_code=400, detail="mode must be morning or eod")

    settings = get_settings()
    repo = ScanRunRepository(session)
    run = None
    if payload.scan_run_id is not None:
        run = await repo.get_by_id(payload.scan_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Scan run not found")
    else:
        for candidate in await repo.list_recent(limit=20):
            status = (candidate.status or "").upper()
            if status == SCAN_STATUS_COMPLETED.upper() and candidate.result_payload:
                run = candidate
                break
        if run is None:
            raise HTTPException(status_code=404, detail="No completed scan yet. Run Find Setups first.")

    if (run.status or "").upper() != SCAN_STATUS_COMPLETED.upper():
        raise HTTPException(status_code=409, detail="Scan is not completed yet")
    if not run.result_payload or not isinstance(run.result_payload, dict):
        raise HTTPException(status_code=404, detail="Scan payload missing")

    alert, result = await send_brief_email(
        run.result_payload,
        mode=mode,  # type: ignore[arg-type]
        scan_run_id=run.id,
        settings=settings,
    )

    target = resolve_smtp_target(settings)
    recipients: list[str] = []
    provider: str | None = None
    if not isinstance(target, str):
        recipients = list(target.recipients)
        provider = target.provider

    if not result.email_sent:
        raise HTTPException(
            status_code=503,
            detail=result.detail or "Email was not sent",
        )

    return SendBriefResponse(
        email_sent=True,
        detail=result.detail,
        subject=alert.title,
        recipients=recipients,
        scan_run_id=run.id,
        provider=provider,
    )
