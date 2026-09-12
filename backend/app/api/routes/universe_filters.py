"""Universe filters + presets API (sellable EP1)."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.domain.intraday.asset_class import classify_asset_class
from app.domain.universe.filters import FILTER_PRESETS, UniverseFilterSpec, filter_symbols
from app.infrastructure.database.models import CandleORM, InstrumentORM
from app.infrastructure.universe import get_universe
from app.infrastructure.universe.static_file_universe import SUPPORTED_UNIVERSE_NAMES

router = APIRouter(prefix="/api/v1/universe", tags=["universe"])

_REASON_COPY: dict[str, tuple[str, str]] = {
    "SURVEILLANCE": ("Surveillance", "ASM / surveillance block"),
    "CORPORATE_ACTION": ("CA day", "Corporate action day block"),
    "ASSET_CLASS": ("Filtered", "Asset class does not match filter"),
    "SECTOR": ("Filtered", "Sector not in selected list"),
    "MIN_PRICE": ("Filtered", "Below minimum price threshold"),
    "MAX_PRICE": ("Filtered", "Above maximum price threshold"),
    "MIN_ADV": ("Filtered", "Below minimum ADV threshold"),
    "NO_CANDLES": ("No 1d candles", "Missing daily price data"),
}


@router.get("/supported")
async def supported_universes() -> dict:
    return {"universes": list(SUPPORTED_UNIVERSE_NAMES), "default": "NSE_ALL"}


@router.get("/symbols")
async def search_universe_symbols(
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    universe: str = Query(default="NSE_ALL"),
) -> dict:
    """Prefix/contains autocomplete over a packaged NSE universe."""
    query = (q or "").strip().upper()
    universe_name = (universe or "NSE_ALL").strip().upper()
    if universe_name not in SUPPORTED_UNIVERSE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"universe must be one of: {', '.join(SUPPORTED_UNIVERSE_NAMES)}",
        )
    try:
        snap = get_universe(universe_name).get_snapshot()
    except Exception as exc:  # pragma: no cover - file/config errors
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    symbols = list(snap.symbols)
    if query:
        starts = [s for s in symbols if s.startswith(query)]
        contains = [s for s in symbols if query in s and not s.startswith(query)]
        ranked = starts + contains
    else:
        ranked = symbols

    matches = ranked[:limit]
    return {
        "universe": snap.name,
        "universe_version": snap.version,
        "query": query,
        "count": len(matches),
        "symbols": [
            {"symbol": sym, "asset_class": classify_asset_class(sym)} for sym in matches
        ],
    }


@router.get("/presets")
async def filter_presets() -> dict:
    return {
        "presets": {
            key: spec.to_dict()
            for key, spec in FILTER_PRESETS.items()
        }
    }


async def _latest_1d_metrics(
    session: AsyncSession,
    symbols: list[str],
) -> tuple[dict[str, Decimal], dict[str, Decimal], int]:
    """Last 1d close + rough ADV (close × volume) for filter preview."""
    if not symbols:
        return {}, {}, 0
    sample = symbols if len(symbols) <= 4000 else symbols[:4000]
    latest_ts = (
        select(
            CandleORM.instrument_id.label("instrument_id"),
            func.max(CandleORM.timestamp).label("max_ts"),
        )
        .where(CandleORM.timeframe == "1d")
        .group_by(CandleORM.instrument_id)
        .subquery()
    )
    stmt = (
        select(InstrumentORM.symbol, CandleORM.close, CandleORM.volume)
        .join(
            latest_ts,
            and_(
                CandleORM.instrument_id == latest_ts.c.instrument_id,
                CandleORM.timestamp == latest_ts.c.max_ts,
            ),
        )
        .join(InstrumentORM, InstrumentORM.id == CandleORM.instrument_id)
        .where(CandleORM.timeframe == "1d")
        .where(InstrumentORM.symbol.in_(sample))
    )
    result = await session.execute(stmt)
    prices: dict[str, Decimal] = {}
    advs: dict[str, Decimal] = {}
    for symbol, close, volume in result.fetchall():
        sym = str(symbol).strip().upper()
        if not sym or close is None:
            continue
        px = close if isinstance(close, Decimal) else Decimal(str(close))
        prices[sym] = px
        if volume is not None:
            advs[sym] = px * Decimal(int(volume))
    return prices, advs, len(prices)


async def _symbols_with_1d(session: AsyncSession, symbols: list[str] | None = None) -> set[str]:
    """Symbols that have any 1d candle. When ``symbols`` is set, scope to that universe only."""
    stmt = (
        select(InstrumentORM.symbol)
        .join(CandleORM, CandleORM.instrument_id == InstrumentORM.id)
        .where(CandleORM.timeframe == "1d")
    )
    if symbols:
        stmt = stmt.where(InstrumentORM.symbol.in_(list(symbols)))
    stmt = stmt.distinct()
    result = await session.execute(stmt)
    return {str(row[0]).strip().upper() for row in result.fetchall() if row[0]}


@router.post("/preview")
async def preview_filters(
    payload: dict,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Return how many symbols survive filters for a universe (no strategy run)."""
    universe_name = str(payload.get("universe") or "NSE_ALL")
    try:
        snap = get_universe(universe_name).get_snapshot()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    spec = UniverseFilterSpec.from_mapping(
        payload.get("filters") if isinstance(payload.get("filters"), dict) else payload
    )
    need_quotes = (
        spec.min_price is not None or spec.max_price is not None or spec.min_adv_inr is not None
    )
    prices: dict[str, Decimal] = {}
    advs: dict[str, Decimal] = {}
    quotes_coverage = 0
    if need_quotes:
        try:
            prices, advs, quotes_coverage = await _latest_1d_metrics(session, list(snap.symbols))
        except Exception:
            prices, advs, quotes_coverage = {}, {}, 0

    kept, decisions = filter_symbols(
        snap.symbols,
        spec,
        last_price_by_symbol=prices or None,
        adv_by_symbol=advs or None,
    )
    drop_reasons: dict[str, int] = {}
    for d in decisions:
        if not d.kept and d.reason:
            drop_reasons[d.reason] = drop_reasons.get(d.reason, 0) + 1
    equity = sum(1 for s in snap.symbols if classify_asset_class(s) == "STOCK")
    etf = sum(1 for s in snap.symbols if classify_asset_class(s) == "ETF")
    return {
        "universe": snap.name,
        "universe_version": snap.version,
        "universe_total": len(snap.symbols),
        "after_filters": len(kept),
        "equity_count": equity,
        "etf_count": etf,
        "drop_reasons": drop_reasons,
        "filters": spec.to_dict(),
        "sample_kept": kept[:25],
        "quotes_applied": need_quotes and quotes_coverage > 0,
        "quotes_coverage": quotes_coverage,
    }


@router.post("/coverage")
async def coverage_report(
    payload: dict,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Unified skip coverage for Swing/Intraday filter layer (UC-B4)."""
    universe_name = str(payload.get("universe") or "NSE_ALL")
    try:
        snap = get_universe(universe_name).get_snapshot()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    spec = UniverseFilterSpec.from_mapping(
        payload.get("filters") if isinstance(payload.get("filters"), dict) else payload
    )
    limit = int(payload.get("limit") or 400)
    limit = max(50, min(limit, 2000))

    need_quotes = (
        spec.min_price is not None or spec.max_price is not None or spec.min_adv_inr is not None
    )
    prices: dict[str, Decimal] = {}
    advs: dict[str, Decimal] = {}
    if need_quotes:
        try:
            prices, advs, _ = await _latest_1d_metrics(session, list(snap.symbols))
        except Exception:
            prices, advs = {}, {}

    kept, decisions = filter_symbols(
        snap.symbols,
        spec,
        last_price_by_symbol=prices or None,
        adv_by_symbol=advs or None,
    )

    try:
        with_candles = await _symbols_with_1d(session, list(snap.symbols))
    except Exception:
        with_candles = set()

    rows: list[dict[str, str]] = []
    summary = {
        "eligible": 0,
        "filtered": 0,
        "no_candles": 0,
        "surveillance": 0,
        "ca_day": 0,
        "universe_total": len(snap.symbols),
        "after_filters": len(kept),
    }

    for d in decisions:
        if not d.kept and d.reason:
            bucket, reason = _REASON_COPY.get(
                d.reason, ("Filtered", d.reason.replace("_", " ").title())
            )
            if d.reason == "SURVEILLANCE":
                summary["surveillance"] += 1
            elif d.reason == "CORPORATE_ACTION":
                summary["ca_day"] += 1
            else:
                summary["filtered"] += 1
            rows.append(
                {"symbol": d.symbol, "bucket": bucket, "reason": reason, "code": d.reason}
            )

    for sym in kept:
        if sym in with_candles:
            summary["eligible"] += 1
        else:
            summary["no_candles"] += 1
            bucket, reason = _REASON_COPY["NO_CANDLES"]
            rows.append(
                {"symbol": sym, "bucket": bucket, "reason": reason, "code": "NO_CANDLES"}
            )

    priority = {"SURVEILLANCE": 0, "CORPORATE_ACTION": 1, "NO_CANDLES": 2}
    rows.sort(key=lambda r: (priority.get(r.get("code", ""), 9), r["symbol"]))
    truncated = len(rows) > limit

    return {
        "universe": snap.name,
        "universe_version": snap.version,
        "filters": spec.to_dict(),
        "summary": summary,
        "rows": rows[:limit],
        "rows_total": len(rows),
        "truncated": truncated,
        "note": "Unified coverage for Swing and Intraday.",
    }
