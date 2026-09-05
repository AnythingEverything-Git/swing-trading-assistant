"""Groww-style research endpoints for stock detail tabs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_db, get_query_service, get_upstox_provider
from app.api.schemas import (
    FnoResearchResponse,
    IndicatorReadingResponse,
    InsightSectionResponse,
    NewsEventsResearchResponse,
    NewsItemResponse,
    OptionChainRowResponse,
    OverviewResearchResponse,
    PerformancePointResponse,
    PivotLevelsResponse,
    PlanDeductionRephraseRequest,
    PlanDeductionRephraseResponse,
    PlanDeductionStepPayload,
    ResearchInsightRequest,
    ResearchInsightResponse,
    SimilarSetupItemResponse,
    SimilarSetupsResponse,
    TechnicalResearchResponse,
)
from app.application.market_data.query_service import MarketDataQueryService
from app.application.narrative.deduction_rephraser import DeductionRephraser, normalize_steps
from app.application.narrative.gemini_narrator import GeminiNarrator
from app.application.narrative.insight_cache import (
    get_cached_insight,
    insight_cache_key,
    put_cached_insight,
)
from app.application.research.overview_service import build_overview_snapshot
from app.application.research.technical_service import build_technical_snapshot
from app.core.config import get_settings
from app.infrastructure.news.nse_news_provider import NseNewsProvider

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def _default_range(end: datetime | None, start: datetime | None) -> tuple[datetime, datetime]:
    resolved_end = end or datetime.now(timezone.utc)
    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)
    resolved_start = start or (resolved_end - timedelta(days=400))
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=timezone.utc)
    if resolved_start > resolved_end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    return resolved_start, resolved_end


@router.get("/{symbol}/overview", response_model=OverviewResearchResponse)
async def research_overview(
    symbol: str,
    request: Request,
    timeframe: str = Query("1d"),
    start: datetime | None = None,
    end: datetime | None = None,
    svc: MarketDataQueryService = Depends(get_query_service),
) -> OverviewResearchResponse:
    resolved_start, resolved_end = _default_range(end, start)
    candles = await svc.get_candles(symbol.upper(), timeframe, resolved_start, resolved_end)
    snapshot = build_overview_snapshot(symbol.upper(), timeframe, candles)

    current_price = None
    change_pct = None
    provider = getattr(request.app.state, "upstox_provider", None)
    quote_fn = getattr(provider, "get_last_traded_prices", None)
    if quote_fn is not None:
        try:
            quotes = await quote_fn([symbol.upper()])
            payload = quotes.get(symbol.upper())
            if payload:
                current_price = payload.get("last_price")
                raw = payload.get("raw") or {}
                net_change = raw.get("net_change")
                if net_change is not None and current_price:
                    net = Decimal(str(net_change))
                    prev = current_price - net
                    if prev != 0:
                        change_pct = (net / prev) * Decimal("100")
        except Exception:
            pass

    return OverviewResearchResponse(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        last_close=snapshot.last_close,
        last_volume=snapshot.last_volume,
        performance=[
            PerformancePointResponse(label=p.label, change_percent=p.change_percent)
            for p in snapshot.performance
        ],
        high_52w=snapshot.high_52w,
        low_52w=snapshot.low_52w,
        candle_count=snapshot.candle_count,
        current_price=current_price,
        current_price_change_percent=change_pct,
    )


@router.get("/{symbol}/technical", response_model=TechnicalResearchResponse)
async def research_technical(
    symbol: str,
    timeframe: str = Query("1d"),
    start: datetime | None = None,
    end: datetime | None = None,
    svc: MarketDataQueryService = Depends(get_query_service),
) -> TechnicalResearchResponse:
    resolved_start, resolved_end = _default_range(end, start)
    candles = await svc.get_candles(symbol.upper(), timeframe, resolved_start, resolved_end)
    snapshot = build_technical_snapshot(symbol.upper(), timeframe, candles)
    pivots = None
    if snapshot.pivots is not None:
        pivots = PivotLevelsResponse(
            pivot=snapshot.pivots.pivot,
            resistance_1=snapshot.pivots.resistance_1,
            resistance_2=snapshot.pivots.resistance_2,
            resistance_3=snapshot.pivots.resistance_3,
            support_1=snapshot.pivots.support_1,
            support_2=snapshot.pivots.support_2,
            support_3=snapshot.pivots.support_3,
        )
    return TechnicalResearchResponse(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        last_close=snapshot.last_close,
        indicators=[
            IndicatorReadingResponse(
                name=item.name,
                value=item.value,
                signal=item.signal,
                detail=item.detail,
            )
            for item in snapshot.indicators
        ],
        pivots=pivots,
        volume_vs_sma=snapshot.volume_vs_sma,
    )


@router.get("/{symbol}/fno", response_model=FnoResearchResponse)
async def research_fno(
    symbol: str,
    expiry: str = Query("current_month"),
    provider=Depends(get_upstox_provider),
) -> FnoResearchResponse:
    chain_fn = getattr(provider, "get_option_chain", None)
    if chain_fn is None:
        return FnoResearchResponse(
            symbol=symbol.upper(),
            expiry_date=expiry,
            status="unavailable",
            detail="Option chain requires live Upstox provider",
        )
    try:
        payload = await chain_fn(symbol.upper(), expiry)
    except Exception as exc:
        return FnoResearchResponse(
            symbol=symbol.upper(),
            expiry_date=expiry,
            status="unavailable",
            detail=str(exc),
        )

    return FnoResearchResponse(
        symbol=payload.get("symbol", symbol.upper()),
        expiry_date=payload.get("expiry_date", expiry),
        expiry=payload.get("expiry"),
        spot=payload.get("spot"),
        pcr=payload.get("pcr"),
        rows=[OptionChainRowResponse(**row) for row in payload.get("rows", [])],
        status="ok",
    )


@router.get("/{symbol}/news-events", response_model=NewsEventsResearchResponse)
async def research_news_events(symbol: str) -> NewsEventsResearchResponse:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        snapshot = await NseNewsProvider(client).get_news_events(symbol.upper())
    return NewsEventsResearchResponse(
        symbol=snapshot.symbol,
        announcements=[
            NewsItemResponse(
                title=item.title,
                published_at=item.published_at,
                source=item.source,
                category=item.category,
                url=item.url,
            )
            for item in snapshot.announcements
        ],
        events=[
            NewsItemResponse(
                title=item.title,
                published_at=item.published_at,
                source=item.source,
                category=item.category,
                url=item.url,
            )
            for item in snapshot.events
        ],
        status=snapshot.status,
        detail=snapshot.detail,
    )


@router.post("/{symbol}/insight", response_model=ResearchInsightResponse)
async def research_insight(
    symbol: str,
    payload: ResearchInsightRequest,
) -> ResearchInsightResponse:
    context = dict(payload.context or {})
    context.setdefault("symbol", symbol.upper())
    tab = (payload.tab or "overview").strip().lower()
    if tab not in {"overview", "technical", "news", "setup", "fno"}:
        raise HTTPException(status_code=400, detail="tab must be overview|technical|news|setup|fno")

    cache_key = insight_cache_key(symbol, tab, context)
    cached = get_cached_insight(cache_key)
    if cached is not None:
        return ResearchInsightResponse(
            title=cached.title,
            headline=cached.headline,
            bullets=list(cached.bullets),
            sections=[InsightSectionResponse(label=s.label, text=s.text) for s in cached.sections],
            provider=cached.provider,
            grounded=cached.grounded,
            detail=cached.detail,
            cached=True,
        )

    async with httpx.AsyncClient() as client:
        result = await GeminiNarrator(client, get_settings()).generate_insight(tab=tab, context=context)
    put_cached_insight(cache_key, result)
    return ResearchInsightResponse(
        title=result.title,
        headline=result.headline,
        bullets=list(result.bullets),
        sections=[InsightSectionResponse(label=s.label, text=s.text) for s in result.sections],
        provider=result.provider,
        grounded=result.grounded,
        detail=result.detail,
        cached=False,
    )


@router.post("/plan-deduction/rephrase", response_model=PlanDeductionRephraseResponse)
async def rephrase_plan_deduction(
    payload: PlanDeductionRephraseRequest,
) -> PlanDeductionRephraseResponse:
    """Polish beginner wording only. Numbers and strategy facts stay locked to the request."""
    source = normalize_steps([step.model_dump() for step in payload.steps])
    if not source:
        raise HTTPException(status_code=400, detail="steps required")

    async with httpx.AsyncClient() as client:
        result = await DeductionRephraser(client, get_settings()).rephrase(
            symbol=payload.symbol,
            steps=source,
        )

    return PlanDeductionRephraseResponse(
        symbol=payload.symbol.upper().strip(),
        steps=[
            PlanDeductionStepPayload(
                id=step.id,
                title=step.title,
                value=step.value,
                summary=step.summary,
                details=list(step.details),
            )
            for step in result.steps
        ],
        provider=result.provider,
        grounded=result.grounded,
        detail=result.detail,
    )


@router.get("/{symbol}/similar-setups", response_model=SimilarSetupsResponse)
async def similar_setups(
    symbol: str,
    direction: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    forward_bars: int = Query(default=10, ge=3, le=30),
    session=Depends(get_db),
    query: MarketDataQueryService = Depends(get_query_service),
) -> SimilarSetupsResponse:
    """Deterministic similar-setup retrieval from historical ScanRuns + candle forward path."""
    from app.application.narrative.grounded_narrator import GroundedNarrator, narrative_llm_enabled
    from app.application.research.similar_setups import (
        fingerprint_from_opportunity_payload,
        forward_outcome_from_candles,
        rank_similar,
        similar_blurb,
        SetupFingerprint,
    )
    from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository

    symbol_u = symbol.upper().strip()
    runs = await ScanRunRepository(session).list_recent(limit=40)
    corpus: list[SetupFingerprint] = []
    query_fp: SetupFingerprint | None = None

    for run in runs:
        payload = run.result_payload or {}
        for item in list(payload.get("opportunities") or []):
            fp = fingerprint_from_opportunity_payload(item, scan_run_id=run.id)
            if fp is None:
                continue
            corpus.append(fp)
            if fp.symbol == symbol_u and (direction is None or fp.direction == direction.upper()):
                if query_fp is None or fp.confirmation_time > query_fp.confirmation_time:
                    query_fp = fp

    if query_fp is None:
        # Synthetic query from latest same-direction peer average placeholders is not allowed —
        # require an observed setup for this symbol in scan history.
        return SimilarSetupsResponse(symbol=symbol_u, direction=direction, matches=[], provider="template")

    neighbors = rank_similar(query_fp, corpus, limit=limit)
    settings = get_settings()
    matches: list[SimilarSetupItemResponse] = []
    narrator = None
    client = None
    if narrative_llm_enabled(settings):
        client = httpx.AsyncClient(timeout=20.0)
        narrator = GroundedNarrator(client, settings)
    try:
        for peer, distance in neighbors:
            start = peer.confirmation_time - timedelta(days=5)
            end = max(
                peer.confirmation_time + timedelta(days=max(forward_bars * 3, 40)),
                datetime.now(timezone.utc),
            )
            try:
                candles = await query.get_candles(peer.symbol, "1d", start, end)
            except Exception:
                candles = []
            ret, hit_t, hit_s = forward_outcome_from_candles(
                candles,
                confirmation_time=peer.confirmation_time,
                direction=peer.direction,
                entry=peer.entry,
                stop=peer.stop,
                target=peer.target,
                forward_bars=forward_bars,
            )
            measured_bars = forward_bars
            if ret is None and candles:
                # Fall back to whatever post-confirmation bars exist.
                ret, hit_t, hit_s = forward_outcome_from_candles(
                    candles,
                    confirmation_time=peer.confirmation_time,
                    direction=peer.direction,
                    entry=peer.entry,
                    stop=peer.stop,
                    target=peer.target,
                    forward_bars=max(1, min(forward_bars, len(candles))),
                )
                if ret is not None:
                    measured_bars = max(1, min(forward_bars, len(candles) - 1))
            blurb = await similar_blurb(
                narrator,
                match=peer,
                forward_return_pct=ret,
                forward_bars=measured_bars,
            )
            matches.append(
                SimilarSetupItemResponse(
                    symbol=peer.symbol,
                    direction=peer.direction,
                    confirmation_time=peer.confirmation_time,
                    quality_score=peer.quality_score,
                    atr_percent=peer.atr_percent,
                    risk_reward_ratio=peer.risk_reward_ratio,
                    distance=distance,
                    forward_bars=measured_bars,
                    forward_return_pct=ret,
                    hit_target=hit_t,
                    hit_stop=hit_s,
                    blurb=blurb.text,
                    blurb_provider=blurb.provider,
                    scan_run_id=peer.scan_run_id,
                )
            )
    finally:
        if client is not None:
            await client.aclose()

    return SimilarSetupsResponse(
        symbol=symbol_u,
        direction=query_fp.direction,
        matches=matches,
        provider="llm" if any(m.blurb_provider == "llm" for m in matches) else "template",
    )
