"""Intraday ORB session API (parallel to swing scan)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_query_service, get_upstox_provider
from app.application.intraday.board_cache import job_status, serve_morning_board
from app.application.intraday.session_service import (
    load_session,
    load_session_chart,
    run_intraday_session,
    session_report_to_dict,
)
from app.application.market_data.query_service import MarketDataQueryService
from app.infrastructure.database.repositories.intraday_session_repository import (
    IntradaySessionRepository,
)

router = APIRouter(prefix="/api/v1/intraday", tags=["intraday"])


class IntradaySessionRunRequest(BaseModel):
    session_date: date | None = None
    symbols: list[str] | None = None
    universe: Literal[
        "DEMO_SAMPLE",
        "NIFTY_50",
        "NIFTY_100",
        "NIFTY_200",
        "NIFTY_500",
        "NSE_ETF",
        "NSE_CASH",
        "NSE_ALL",
        "NSE_MORNING",
    ] | None = None
    equity: Decimal = Field(default=Decimal("1000000"))
    source: Literal["demo", "persisted"] = "demo"
    sync: bool = Field(default=False, description="When true, block until session completes (tests).")


@router.get("/rules")
async def get_rules() -> dict:
    """Frozen CONFIG_V1 facts for the Intraday desk (beginner + power-user)."""
    from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1, STRATEGY_ID, CONFIG_HASH

    c = DEFAULT_CONFIG_V1
    return {
        "strategy_id": STRATEGY_ID,
        "config_hash": CONFIG_HASH,
        "beginner": {
            "title": "Same-day opening-range breakout",
            "summary": (
                "Watch the first 5 minutes (09:15–09:20), rank busy names by relative volume, "
                "enter only on a 1-minute breakout, protect with a safety exit, and flatten by 15:10. "
                "V1 has no profit goal."
            ),
            "steps": [
                "Opening range: 09:15–09:20 IST",
                "Screen: RVOL5 ≥ 1.0, Top 20 armed",
                "Entry: 1m close beyond OR (before 14:30)",
                "Safety exit: ~0.10 × prior ATR14 (bounded)",
                "Size: ~0.5% of capital at risk per trade (max 3 open)",
                "Exit: hit safety exit or forced flatten 15:10 — no overnight",
            ],
        },
        "locks": {
            "or_window": "09:15–09:20",
            "entry_cutoff": "14:30",
            "forced_exit": "15:10",
            "min_rvol5": str(c.min_rvol5),
            "top_n": c.top_n,
            "risk_per_trade_pct": str(c.risk_per_trade_pct),
            "max_concurrent": c.max_concurrent,
            "max_open_risk_pct": str(c.max_open_risk_pct),
            "daily_loss_lock_pct": str(c.daily_loss_lock_pct),
            "consecutive_loss_lock": c.consecutive_loss_lock,
            "stop_atr_mult": str(c.stop_atr_mult),
            "no_profit_target": True,
        },
    }


def _session_repo(db: AsyncSession = Depends(get_db)) -> IntradaySessionRepository:
    return IntradaySessionRepository(db)


def _resolve_symbols(payload: IntradaySessionRunRequest) -> list[str] | None:
    if payload.symbols:
        return payload.symbols
    if payload.universe in (None, "DEMO_SAMPLE"):
        return None
    if payload.universe in ("NSE_MORNING", "NSE_ALL"):
        from app.domain.intraday.asset_class import morning_universe_symbols

        ordered, _classes = morning_universe_symbols()
        return list(ordered)
    from app.infrastructure.universe import get_universe

    try:
        universe = get_universe(payload.universe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return list(universe.get_snapshot().symbols)


@router.post("/sessions/run")
async def run_session(
    payload: IntradaySessionRunRequest,
    request: Request,
    query: MarketDataQueryService = Depends(get_query_service),
    session_repo: IntradaySessionRepository = Depends(_session_repo),
) -> JSONResponse:
    """Run ORB session. Default async 202; ``sync=true`` for tests keeps full blocking accuracy."""
    import asyncio

    from app.infrastructure.database.repositories.candle_repository import CandleRepository
    from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository

    sync = bool(payload.sync)
    try:
        symbols = _resolve_symbols(payload)
    except HTTPException:
        raise

    if sync:
        try:
            session_id, report, meta = await run_intraday_session(
                session_date=payload.session_date,
                symbols=symbols,
                equity=payload.equity,
                source=payload.source,
                query=query if payload.source == "persisted" else None,
                session_repo=session_repo,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        body = session_report_to_dict(report, meta)
        body["id"] = session_id
        return JSONResponse(status_code=200, content=_jsonable(body))

    job_id = f"session-{int(asyncio.get_event_loop().time() * 1000)}"
    jobs = getattr(request.app.state, "session_run_jobs", None)
    if not isinstance(jobs, dict):
        jobs = {}
        request.app.state.session_run_jobs = jobs
    jobs[job_id] = {"status": "queued"}

    sessionmaker = request.app.state.sessionmaker
    src = payload.source
    equity = payload.equity
    session_date = payload.session_date

    async def _run() -> None:
        jobs[job_id]["status"] = "running"
        try:
            async with sessionmaker() as session:
                q = (
                    MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
                    if src == "persisted"
                    else None
                )
                repo = IntradaySessionRepository(session)
                session_id, report, meta = await run_intraday_session(
                    session_date=session_date,
                    symbols=symbols,
                    equity=equity,
                    source=src,
                    query=q,
                    session_repo=repo,
                )
                await session.commit()
            body = session_report_to_dict(report, meta)
            body["id"] = session_id
            jobs[job_id]["status"] = "ready"
            jobs[job_id]["session_id"] = session_id
            jobs[job_id]["result"] = _jsonable(body)
        except Exception as exc:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)[:400]

    asyncio.create_task(_run(), name=job_id)
    return JSONResponse(
        status_code=202,
        content={"accepted": True, "job_id": job_id, "status": "queued"},
    )


@router.get("/sessions/jobs/{job_id}")
async def session_run_job(job_id: str, request: Request) -> dict:
    jobs = getattr(request.app.state, "session_run_jobs", {}) or {}
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, **job}


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    session_repo: IntradaySessionRepository = Depends(_session_repo),
) -> dict:
    rows = await session_repo.list_recent(limit=min(max(limit, 1), 100))
    return {
        "sessions": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "session_date": row.session_date.isoformat(),
                "strategy_id": row.strategy_id,
                "config_hash": row.config_hash,
                "data_source": row.data_source,
                "coverage_eligible": row.coverage_eligible,
                "coverage_total": row.coverage_total,
                "fill_count": row.fill_count,
                "realized_pnl": str(row.realized_pnl) if row.realized_pnl is not None else None,
            }
            for row in rows
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    session_repo: IntradaySessionRepository = Depends(_session_repo),
) -> dict:
    stored = await load_session(session_id, session_repo=session_repo)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if stored.get("result_payload"):
        body = dict(stored["result_payload"])
        body["id"] = stored["id"]
        body["created_at"] = stored["created_at"]
        return body
    report = stored.get("report")
    if report is None:
        raise HTTPException(status_code=404, detail="Session payload missing")
    body = session_report_to_dict(report, stored.get("meta"))
    body["id"] = stored["id"]
    body["created_at"] = stored["created_at"]
    return body


@router.get("/sessions/{session_id}/chart/{symbol}")
async def get_session_chart(
    session_id: str,
    symbol: str,
    timeframe: Literal["1m", "5m"] = "1m",
    query: MarketDataQueryService = Depends(get_query_service),
    session_repo: IntradaySessionRepository = Depends(_session_repo),
) -> dict:
    try:
        chart = await load_session_chart(
            session_id,
            symbol,
            query=query,
            session_repo=session_repo,
            timeframe=timeframe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if chart is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not chart.get("candles"):
        raise HTTPException(status_code=404, detail="No candles for this symbol/session")
    return chart


class PracticeTickRequest(BaseModel):
    marks: dict[str, Decimal] | None = None
    force_eod: bool = False
    use_live_quotes: bool = True


class PracticeCloseRequest(BaseModel):
    price: Decimal


class MorningRunRequest(BaseModel):
    universe: Literal[
        "DEMO_SAMPLE",
        "NIFTY_50",
        "NIFTY_100",
        "NIFTY_200",
        "NIFTY_500",
        "NSE_ETF",
        "NSE_CASH",
        "NSE_ALL",
        "NSE_MORNING",
    ] = "NIFTY_500"
    symbols: list[str] | None = None
    equity: Decimal = Field(default=Decimal("1000000"))
    source: Literal["demo", "persisted"] = "persisted"
    seed_practice: bool = True
    session_date: date | None = None


class MorningBoardRequest(BaseModel):
    session_date: date | None = None
    source: Literal["demo", "persisted"] = "persisted"
    equity: Decimal = Field(default=Decimal("1000000"))


def _practice_service(db: AsyncSession = Depends(get_db)):
    from app.application.intraday.practice_service import IntradayPracticeService
    from app.infrastructure.database.repositories.intraday_practice_repository import (
        IntradayPracticeRepository,
    )

    return IntradayPracticeService(IntradayPracticeRepository(db))


def _session_payload(stored: dict) -> dict:
    if stored.get("result_payload"):
        return dict(stored["result_payload"])
    report = stored.get("report")
    if report is None:
        raise HTTPException(status_code=404, detail="Session payload missing")
    return session_report_to_dict(report, stored.get("meta"))


@router.get("/morning-board")
async def morning_board(
    request: Request,
    session_date: date | None = None,
    source: Literal["demo", "persisted"] = "persisted",
    equity: Decimal = Decimal("1000000"),
    asset_class: Literal["ALL", "STOCK", "ETF"] = "ALL",
    min_adv_inr: Decimal | None = None,
    force_refresh: bool = Query(default=False),
    universe: str = Query(default="NIFTY_500"),
) -> JSONResponse:
    """Morning board — cached/SWR for ≤3s HTTP; ranks remain accuracy-identical."""
    filters = {
        "asset_class": asset_class,
        "min_adv_inr": str(min_adv_inr) if min_adv_inr is not None else None,
        "exclude_surveillance": True,
        "exclude_corporate_actions": True,
    }
    try:
        body, status = await serve_morning_board(
            request.app,
            session_date=session_date,
            source=source,
            equity=equity,
            filters=filters,
            universe=universe,
            symbols=None,
            force_refresh=force_refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(status_code=status, content=_jsonable(body))


@router.post("/morning-board")
async def morning_board_post(payload: dict, request: Request) -> JSONResponse:
    """Morning board with full filter body (sellable EP1/EP3)."""
    from datetime import date as date_cls

    session_date = payload.get("session_date")
    day = date_cls.fromisoformat(str(session_date)) if session_date else None
    source = payload.get("source") or "persisted"
    force_refresh = bool(payload.get("force_refresh"))
    try:
        body, status = await serve_morning_board(
            request.app,
            session_date=day,
            source=str(source),
            equity=Decimal(str(payload.get("equity") or "1000000")),
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else payload,
            universe=str(payload.get("universe") or "NIFTY_500"),
            symbols=[str(s).upper() for s in (payload.get("symbols") or []) if str(s).strip()] or None,
            force_refresh=force_refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(status_code=status, content=_jsonable(body))


@router.get("/morning-board/jobs/{job_id}")
async def morning_board_job(job_id: str, request: Request) -> dict:
    status = job_status(request.app, job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="job not found")
    if status.get("status") == "ready":
        from app.application.intraday.board_cache import get_cached_board

        board = get_cached_board(request.app, str(status.get("cache_key") or ""))
        if board is not None:
            return {"job": status, "board": board}
    return {"job": status}


def _jsonable(value):
    """Ensure Decimals/dates become JSON-safe (board payloads already mostly str)."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


@router.post("/ingest/ensure-1m")
async def ensure_1m(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    provider=Depends(get_upstox_provider),
) -> JSONResponse:
    """Hybrid 1m backfill — returns 202 immediately; work runs in background (full accuracy)."""
    import asyncio
    from datetime import date as date_cls

    from app.application.intraday.active_set_ingest import ensure_1m_for_symbols
    from app.infrastructure.database.repositories.candle_repository import CandleRepository
    from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository

    symbols = [str(s).upper() for s in (payload.get("symbols") or []) if str(s).strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols required")
    if len(symbols) > 200:
        symbols = symbols[:200]
    day_raw = payload.get("session_date")
    day = date_cls.fromisoformat(str(day_raw)) if day_raw else None
    sync = bool(payload.get("sync"))
    if sync:
        result = await ensure_1m_for_symbols(
            symbols=symbols,
            provider=provider,
            instrument_repo=InstrumentRepository(db),
            candle_repo=CandleRepository(db),
            session_date=day,
        )
        await db.commit()
        return JSONResponse(status_code=200, content=result)

    job_id = f"ensure1m-{int(asyncio.get_event_loop().time() * 1000)}"
    jobs = getattr(request.app.state, "ensure_1m_jobs", None)
    if not isinstance(jobs, dict):
        jobs = {}
        request.app.state.ensure_1m_jobs = jobs
    jobs[job_id] = {"status": "queued", "symbols": len(symbols)}

    sessionmaker = request.app.state.sessionmaker
    upstox = provider

    async def _run() -> None:
        jobs[job_id]["status"] = "running"
        try:
            async with sessionmaker() as session:
                result = await ensure_1m_for_symbols(
                    symbols=symbols,
                    provider=upstox,
                    instrument_repo=InstrumentRepository(session),
                    candle_repo=CandleRepository(session),
                    session_date=day,
                )
                await session.commit()
            jobs[job_id]["status"] = "ready"
            jobs[job_id]["result"] = result
        except Exception as exc:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)[:400]

    asyncio.create_task(_run(), name=job_id)
    return JSONResponse(
        status_code=202,
        content={"accepted": True, "job_id": job_id, "status": "queued", "symbols": len(symbols)},
    )


@router.get("/ingest/ensure-1m/jobs/{job_id}")
async def ensure_1m_job(job_id: str, request: Request) -> dict:
    jobs = getattr(request.app.state, "ensure_1m_jobs", {}) or {}
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, **job}


@router.post("/sessions/morning")
async def morning_session(
    payload: MorningRunRequest,
    request: Request,
) -> JSONResponse:
    """Morning one-click session — 202 accept; full ORB accuracy runs in background."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.domain.intraday.session_calendar import default_session_date, is_trading_day

    ist = ZoneInfo("Asia/Kolkata")
    day = payload.session_date or default_session_date(datetime.now(tz=ist))
    if not is_trading_day(day):
        raise HTTPException(
            status_code=400,
            detail="Pick a trading day (weekends and NSE holidays are closed)",
        )

    run_payload = IntradaySessionRunRequest(
        session_date=day,
        symbols=payload.symbols,
        universe=None if payload.symbols else payload.universe,
        equity=payload.equity,
        source=payload.source,
        sync=False,
    )
    # Delegate to the same async runner (Depends not needed — we build session inside job).
    import asyncio

    from app.infrastructure.database.repositories.candle_repository import CandleRepository
    from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository

    try:
        symbols = _resolve_symbols(run_payload)
    except HTTPException:
        raise

    job_id = f"morning-session-{int(asyncio.get_event_loop().time() * 1000)}"
    jobs = getattr(request.app.state, "session_run_jobs", None)
    if not isinstance(jobs, dict):
        jobs = {}
        request.app.state.session_run_jobs = jobs
    jobs[job_id] = {"status": "queued"}
    sessionmaker = request.app.state.sessionmaker
    src = payload.source
    equity = payload.equity
    seed_practice = payload.seed_practice

    async def _run() -> None:
        jobs[job_id]["status"] = "running"
        try:
            async with sessionmaker() as session:
                q = (
                    MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
                    if src == "persisted"
                    else None
                )
                repo = IntradaySessionRepository(session)
                session_id, report, meta = await run_intraday_session(
                    session_date=day,
                    symbols=symbols,
                    equity=equity,
                    source=src,
                    query=q,
                    session_repo=repo,
                )
                body = session_report_to_dict(report, meta)
                body["id"] = session_id
                practice_result = None
                if seed_practice and report.fills:
                    from app.application.intraday.practice_service import IntradayPracticeService
                    from app.infrastructure.database.repositories.intraday_practice_repository import (
                        IntradayPracticeRepository,
                    )

                    practice_result = await IntradayPracticeService(
                        IntradayPracticeRepository(session)
                    ).seed_from_session_payload(session_id=session_id, payload=body)
                await session.commit()
            jobs[job_id]["status"] = "ready"
            jobs[job_id]["session_id"] = session_id
            jobs[job_id]["result"] = _jsonable(
                {"session": body, "practice": practice_result, "hint": "Morning one-click session ready"}
            )
        except Exception as exc:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)[:400]

    asyncio.create_task(_run(), name=job_id)
    return JSONResponse(
        status_code=202,
        content={"accepted": True, "job_id": job_id, "status": "queued"},
    )


@router.post("/sessions/{session_id}/practice/seed")
async def seed_practice(
    session_id: str,
    session_repo: IntradaySessionRepository = Depends(_session_repo),
    practice=Depends(_practice_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stored = await load_session(session_id, session_repo=session_repo)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = _session_payload(stored)
    result = await practice.seed_from_session_payload(session_id=session_id, payload=payload)
    await db.commit()
    return result


@router.get("/sessions/{session_id}/practice")
async def list_practice(
    session_id: str,
    practice=Depends(_practice_service),
) -> dict:
    trades = await practice.list_for_session(session_id)
    return {
        "session_id": session_id,
        "trades": trades,
        "claim": "INTRADAY PRACTICE — fake money · stop or 15:10 flatten · no profit goal",
    }


@router.get("/sessions/{session_id}/practice/divergence")
async def practice_divergence(
    session_id: str,
    session_repo: IntradaySessionRepository = Depends(_session_repo),
    practice=Depends(_practice_service),
) -> dict:
    stored = await load_session(session_id, session_repo=session_repo)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = _session_payload(stored)
    return await practice.divergence_vs_session(session_id=session_id, payload=payload)


@router.get("/sessions/{session_id}/practice/reconcile")
async def practice_reconcile(
    session_id: str,
    session_repo: IntradaySessionRepository = Depends(_session_repo),
    practice=Depends(_practice_service),
) -> dict:
    """Restart reconcile stub — compare OPEN practice vs session fills; may halt."""
    from app.application.intraday.reconcile import reconcile_practice_vs_session

    stored = await load_session(session_id, session_repo=session_repo)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = _session_payload(stored)
    trades = await practice.list_for_session(session_id)
    return reconcile_practice_vs_session(practice_trades=trades, session_payload=payload)


@router.post("/sessions/{session_id}/practice/tick")
async def tick_practice(
    session_id: str,
    payload: PracticeTickRequest | None = None,
    practice=Depends(_practice_service),
    db: AsyncSession = Depends(get_db),
    provider=Depends(get_upstox_provider),
) -> dict:
    body = payload or PracticeTickRequest()
    result = await practice.tick(
        session_id=session_id,
        marks=body.marks,
        force_eod=body.force_eod,
        quote_provider=provider if body.use_live_quotes and not body.marks else None,
    )
    await db.commit()
    return result


@router.post("/practice/{trade_id}/close")
async def close_practice(
    trade_id: int,
    payload: PracticeCloseRequest,
    practice=Depends(_practice_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        trade = await practice.close_manual(trade_id, payload.price)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return trade


@router.delete("/practice")
async def reset_intraday_practice(
    practice=Depends(_practice_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start fresh — delete all intraday practice trades."""
    deleted = await practice.reset_all()
    await db.commit()
    return {
        "claim": "PRACTICE — fake money, no real broker orders",
        "deleted": deleted,
        "message": "Intraday practice book cleared. Wallet returns to starting capital.",
    }
