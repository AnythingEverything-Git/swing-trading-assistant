"""Execute a queued scan job end-to-end and persist the result payload."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.scan.scan_response_builder import (
    enrich_current_prices_with_provider,
    to_scan_response,
)
from app.application.alerts.brief_builder import build_scan_brief
from app.application.narrative.grounded_narrator import GroundedNarrator, narrative_llm_enabled
from app.application.paper import PaperTradeService
from app.application.product.status_service import ProductStatusService
from app.application.scan.scan_ai_enrichment import enrich_presented_scan
from app.application.scan.scan_presentation import present_scan
from app.application.scan.universe_scan_report_service import UniverseScanReportService
from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
from app.core.config import get_settings
from app.domain.entities.scan_run import SCAN_STATUS_QUEUED
from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.paper_trade_repository import PaperTradeRepository
from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository
from app.application.market_data.query_service import MarketDataQueryService
from app.infrastructure.universe import get_universe
from app.infrastructure.market_data.source import data_claim

import httpx

logger = logging.getLogger(__name__)

_PAPER_CLAIM = "PRACTICE TRADES ONLY — fake money, no real broker orders"


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


async def execute_scan_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    scan_run_id: int,
    quote_provider: Any | None = None,
) -> None:
    """Load ScanRun parameters, run the universe scan, and write result_payload."""
    async with sessionmaker() as session:
        repo = ScanRunRepository(session)
        run = None
        for attempt in range(8):
            run = await repo.get_by_id(scan_run_id)
            if run is not None:
                break
            await session.rollback()
            await asyncio.sleep(0.05 * (attempt + 1))
        if run is None:
            logger.warning("Scan job %s not found", scan_run_id)
            return
        if run.status != SCAN_STATUS_QUEUED:
            logger.info("Scan job %s skipped (status=%s)", scan_run_id, run.status)
            return

        await repo.mark_running(scan_run_id)
        await session.commit()

        params = run.parameters or {}
        try:
            universe_name = str(params.get("universe_name") or "NIFTY_500")
            timeframe = str(params.get("timeframe") or "1d")
            start = _parse_dt(params["start"])
            end = _parse_dt(params["end"])
            top_n = int(params.get("top_n") or 5)
            min_score = _decimal_or_none(params.get("min_score"))
            account_equity = _decimal_or_none(params.get("account_equity"))
            risk_percent = _decimal_or_none(params.get("risk_percent")) or Decimal("1")
            enable_paper = bool(params.get("enable_paper_trading"))

            universe = get_universe(universe_name)
            snapshot = universe.get_snapshot()

            query = MarketDataQueryService(
                InstrumentRepository(session),
                CandleRepository(session),
            )
            evaluation = StrategyEvaluationService(query, BreakoutRetestConfirmationStrategy())
            report = await UniverseScanReportService(evaluation).scan_universe(
                universe, timeframe, start, end
            )
            presented = present_scan(
                report,
                account_equity=account_equity,
                risk_percent=risk_percent if account_equity is not None else None,
                top_n=top_n,
                min_score=min_score,
            )
            settings = get_settings()
            presented, dq_bullets, _provider = await enrich_presented_scan(
                presented, settings=settings
            )
            ai_brief = None
            if narrative_llm_enabled(settings):
                async with httpx.AsyncClient(timeout=30.0) as client:
                    narrator = GroundedNarrator(client, settings)
                    brief = await build_scan_brief(
                        narrator,
                        presented,
                        mode="premarket",
                        data_claim=data_claim(settings),
                    )
                    ai_brief = brief.text
            else:
                brief = await build_scan_brief(
                    None,
                    presented,
                    mode="premarket",
                    data_claim=data_claim(settings),
                )
                ai_brief = brief.text

            last_candle_time = None
            try:
                status = await ProductStatusService(CandleRepository(session)).status(timeframe)
                last_candle_time = status.last_candle_time
            except Exception:
                last_candle_time = None

            response = to_scan_response(
                presented=presented,
                universe_name=snapshot.name,
                universe_version=snapshot.version,
                timeframe=timeframe,
                start=start,
                end=end,
                scan_run_id=scan_run_id,
                last_candle_time=last_candle_time,
                data_quality_bullets=dq_bullets,
                ai_brief=ai_brief,
            )
            response.status = "completed"
            await enrich_current_prices_with_provider(response, quote_provider)

            if enable_paper:
                try:
                    paper_svc = PaperTradeService(
                        PaperTradeRepository(session),
                        quote_provider=quote_provider,
                    )
                    paper_result = await paper_svc.open_from_scan(response)
                    response.paper_opened_count = paper_result.opened
                    response.paper_skipped_count = paper_result.skipped_qty + paper_result.skipped_open
                    response.paper_claim = _PAPER_CLAIM
                except Exception:
                    logger.exception("Paper seed failed for scan_run_id=%s", scan_run_id)
                    response.paper_opened_count = 0
                    response.paper_skipped_count = 0
                    response.paper_claim = _PAPER_CLAIM
            else:
                response.paper_opened_count = 0
                response.paper_skipped_count = 0
                response.paper_claim = None

            finished_at = datetime.now(timezone.utc)
            metadata = {
                "symbols_scanned": report.symbols_scanned,
                "eligible_count": report.eligible_count,
                "forming_count": report.forming_count,
                "no_setup_count": report.no_setup_count,
                "unavailable_count": report.unavailable_count,
                "error_count": report.error_count,
                "issues_recorded": len(report.issues),
                "data_source": response.data_source,
            }
            await repo.mark_completed(
                scan_run_id,
                finished_at=finished_at,
                result_count=report.eligible_count,
                metadata=metadata,
                result_payload=response.model_dump(mode="json"),
            )
            await session.commit()
        except Exception as exc:
            logger.exception("Scan job %s failed", scan_run_id)
            await session.rollback()
            async with sessionmaker() as fail_session:
                fail_repo = ScanRunRepository(fail_session)
                await fail_repo.mark_failed(
                    scan_run_id,
                    finished_at=datetime.now(timezone.utc),
                    error_message=str(exc) or type(exc).__name__,
                )
                await fail_session.commit()


async def execute_scan_job_for_app(app: FastAPI, scan_run_id: int) -> None:
    sessionmaker = getattr(app.state, "sessionmaker", None)
    if sessionmaker is None:
        raise RuntimeError("Database sessionmaker not configured")
    quote_provider = getattr(app.state, "upstox_provider", None) or getattr(
        app.state, "ingest_provider", None
    )
    await execute_scan_job(
        sessionmaker=sessionmaker,
        scan_run_id=scan_run_id,
        quote_provider=quote_provider,
    )
