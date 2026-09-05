"""Run a universe scan via the shared scan job service, then deliver email alert.

    python scripts/run_scheduled_scan.py --universe NIFTY_50
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.api.schemas import OpportunityScanResponse
from app.application.alerts.composer import ScanAlert
from app.application.alerts import deliver_alert
from app.application.market_data.demo_universe_seed_service import default_demo_seed_range
from app.application.scan.scan_job_service import execute_scan_job
from app.core.config import get_settings
from app.domain.entities.scan_run import SCAN_STATUS_COMPLETED, SCAN_STATUS_QUEUED
from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository
from app.infrastructure.database.session import create_engine, create_sessionmaker
from app.infrastructure.universe import get_universe


def _parse_iso_date(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def run_scan(
    *,
    universe_name: str,
    start: datetime | None,
    end: datetime | None,
    account_equity: Decimal | None,
    risk_percent: Decimal,
    top_n: int,
    brief_mode: str = "premarket",
) -> None:
    settings = get_settings()
    default_start, default_end = default_demo_seed_range()
    resolved_end = end or default_end
    resolved_start = start or default_start
    universe = get_universe(universe_name)
    snapshot = universe.get_snapshot()

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            started_at = datetime.now(timezone.utc)
            scan_run = await ScanRunRepository(session).create(
                started_at=started_at,
                finished_at=None,
                universe_date=resolved_end,
                universe_version=snapshot.version,
                parameters={
                    "universe_name": snapshot.name,
                    "universe_version": snapshot.version,
                    "timeframe": "1d",
                    "start": resolved_start.isoformat(),
                    "end": resolved_end.isoformat(),
                    "top_n": top_n,
                    "min_score": None,
                    "account_equity": str(account_equity) if account_equity is not None else None,
                    "risk_percent": str(risk_percent),
                    "enable_paper_trading": False,
                    "scheduled": True,
                },
                result_count=0,
                status=SCAN_STATUS_QUEUED,
            )
            await session.commit()
            scan_run_id = scan_run.id

        await execute_scan_job(sessionmaker=sessionmaker, scan_run_id=scan_run_id, quote_provider=None)

        async with sessionmaker() as session:
            completed = await ScanRunRepository(session).get_by_id(scan_run_id)
            if completed is None or completed.status != SCAN_STATUS_COMPLETED or not completed.result_payload:
                detail = completed.error_message if completed else "missing"
                raise RuntimeError(f"Scheduled scan failed: {detail}")

            response = OpportunityScanResponse.model_validate(completed.result_payload)
            body = response.alert_preview or f"Scan {scan_run_id} complete"
            open_link = f"{settings.frontend_base_url.rstrip('/')}/?view=scan&run={scan_run_id}"
            if open_link not in body:
                body = f"{body}\n\nOpen this scan: {open_link}"
            alert = ScanAlert(
                title=f"TradePilot {snapshot.name} — {response.eligible_count} eligible ({brief_mode})",
                body=body,
                html_body=None,
            )
            delivery = await deliver_alert(alert, settings)
            print(f"Scheduled scan complete run_id={scan_run_id} source={response.data_source}")
            print(
                f"  eligible={response.eligible_count} forming={response.forming_count} top={len(response.top)}"
            )
            print(f"  alert_logged={delivery.logged} telegram={delivery.telegram_sent}")
            print(alert.body)
    finally:
        await engine.dispose()


async def run_eod_from_latest(*, universe_name: str) -> None:
    """Email the latest completed ScanRun as an EOD brief (no new scan)."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            runs = await ScanRunRepository(session).list_recent(limit=20)
            match = None
            for run in runs:
                if run.status != SCAN_STATUS_COMPLETED or not run.result_payload:
                    continue
                params = run.parameters or {}
                if str(params.get("universe_name") or "") == universe_name or universe_name == "ANY":
                    match = run
                    break
            if match is None:
                raise RuntimeError(f"No completed scan found for {universe_name}")
            response = OpportunityScanResponse.model_validate(match.result_payload)
            body = response.ai_brief or response.alert_preview or f"EOD scan {match.id}"
            if response.data_quality_bullets:
                body = (
                    body
                    + "\n\nData quality notes\n"
                    + "\n".join(f"- {b}" for b in response.data_quality_bullets[:6])
                )
            open_link = f"{settings.frontend_base_url.rstrip('/')}/?view=scan&run={match.id}"
            if open_link not in body:
                body = f"{body}\n\nOpen this scan: {open_link}"
            alert = ScanAlert(
                title=f"TradePilot EOD — {response.eligible_count} eligible",
                body=body,
                html_body=None,
            )
            delivery = await deliver_alert(alert, settings)
            print(f"EOD brief from run_id={match.id} logged={delivery.logged}")
            print(alert.body)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled TradePilot universe scan + alert.")
    parser.add_argument("--universe", default="NIFTY_500")
    parser.add_argument("--start", type=_parse_iso_date, default=None)
    parser.add_argument("--end", type=_parse_iso_date, default=None)
    parser.add_argument("--account-equity", type=Decimal, default=None)
    parser.add_argument("--risk-percent", type=Decimal, default=Decimal("1"))
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument(
        "--brief",
        choices=["premarket", "eod"],
        default="premarket",
        help="Brief mode label for AI/template email copy (eod reuses latest completed run when --reuse-latest).",
    )
    parser.add_argument(
        "--reuse-latest",
        action="store_true",
        help="For --brief eod: email the latest completed ScanRun instead of running a new scan.",
    )
    args = parser.parse_args()
    if args.brief == "eod" and args.reuse_latest:
        _run_async(run_eod_from_latest(universe_name=args.universe))
    else:
        _run_async(
            run_scan(
                universe_name=args.universe,
                start=args.start,
                end=args.end,
                account_equity=args.account_equity,
                risk_percent=args.risk_percent,
                top_n=args.top_n,
                brief_mode=args.brief,
            )
        )


if __name__ == "__main__":
    main()
