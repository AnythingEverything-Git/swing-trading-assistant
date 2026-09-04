"""Groww-style research endpoints for stock detail tabs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_query_service, get_upstox_provider
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
    ResearchInsightRequest,
    ResearchInsightResponse,
    TechnicalResearchResponse,
)
from app.application.market_data.query_service import MarketDataQueryService
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
