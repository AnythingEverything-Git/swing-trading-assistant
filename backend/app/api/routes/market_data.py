from __future__ import annotations

from typing import List
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import MarketDataCandleResponse, MarketQuoteResponse
from app.api.deps import get_query_service, get_upstox_provider
from app.application.market_data.query_service import MarketDataQueryService
from app.api.deps import get_ingestion_service
from app.api.schemas import MarketDataIngestRequest, MarketDataIngestResponse
from fastapi import Body
import time
import logging


router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])


@router.get("/candles/{symbol}", response_model=List[MarketDataCandleResponse])
async def get_candles(
    symbol: str,
    timeframe: str = Query("1d"),
    start: datetime = Query(...),
    end: datetime = Query(...),
    svc: MarketDataQueryService = Depends(get_query_service),
) -> List[MarketDataCandleResponse]:
    # Basic validation
    if start is None or end is None:
        raise HTTPException(status_code=400, detail="start and end are required")
    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end")

    try:
        candles = await svc.get_candles(symbol, timeframe, start, end)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Map domain Candle -> response model
    out: List[MarketDataCandleResponse] = []
    for c in candles:
        out.append(
            MarketDataCandleResponse(
                symbol=c.symbol,
                timeframe=c.timeframe,
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
        )
    return out


@router.get("/quotes", response_model=list[MarketQuoteResponse])
async def get_quotes(
    symbols: str = Query(..., description="Comma-separated symbols, e.g. RELIANCE,TCS"),
    provider=Depends(get_upstox_provider),
) -> list[MarketQuoteResponse]:
    names = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="symbols query parameter is required")

    quote_fn = getattr(provider, "get_last_traded_prices", None)
    if quote_fn is None:
        return [MarketQuoteResponse(symbol=symbol) for symbol in names]

    try:
        raw_quotes = await quote_fn(names)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response: list[MarketQuoteResponse] = []
    for symbol in names:
        payload = raw_quotes.get(symbol) or {}
        last_price = payload.get("last_price")
        price_decimal = Decimal(str(last_price)) if last_price is not None else None
        change_percent = None
        try:
            raw = payload.get("raw", {}) or {}
            net_change = raw.get("net_change")
            if net_change is not None and price_decimal is not None:
                net_change_decimal = Decimal(str(net_change))
                prev_close = price_decimal - net_change_decimal
                if prev_close != 0:
                    change_percent = (net_change_decimal / prev_close) * Decimal("100")
        except Exception:
            change_percent = None
        response.append(
            MarketQuoteResponse(
                symbol=symbol,
                current_price=price_decimal,
                current_price_change_percent=change_percent,
            )
        )
    return response



@router.post("/ingest", response_model=MarketDataIngestResponse)
async def ingest_endpoint(
    payload: MarketDataIngestRequest = Body(...),
    svc = Depends(get_ingestion_service),
) -> MarketDataIngestResponse:
    logger = logging.getLogger("app.ingest")
    start_time = time.perf_counter()

    # Validate timeframe/basic checks already in MarketDataIngestionService
    try:
        fetched_count, persisted_count = await svc.ingest(
            payload.symbol,
            payload.timeframe,
            payload.start,
            payload.end,
        )
        status = "ok"
    except ValueError as exc:
        logger.warning("ingest.invalid: %s %s %s %s", payload.symbol, payload.timeframe, payload.start, payload.end)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("ingest.failed: symbol=%s timeframe=%s start=%s end=%s reason=%s", payload.symbol, payload.timeframe, payload.start, payload.end, str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    duration = time.perf_counter() - start_time
    logger.info(
        "ingest.complete: symbol=%s timeframe=%s start=%s end=%s fetched=%d persisted=%d duration=%.3f",
        payload.symbol,
        payload.timeframe,
        payload.start,
        payload.end,
        fetched_count,
        persisted_count,
        duration,
    )

    return MarketDataIngestResponse(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        candles_fetched=fetched_count,
        candles_persisted=persisted_count,
        status=status,
    )
