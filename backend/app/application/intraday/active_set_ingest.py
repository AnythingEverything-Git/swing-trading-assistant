"""Ensure 1m candles exist for an active symbol set (sellable EP3 hybrid ingest)."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from app.application.market_data.market_data_ingestion_service import MarketDataIngestionService
from app.domain.intraday.session_calendar import combine_ist

IST = ZoneInfo("Asia/Kolkata")


async def ensure_1m_for_symbols(
    *,
    symbols: Sequence[str],
    provider: Any,
    instrument_repo: Any,
    candle_repo: Any,
    session_date: date | None = None,
    pause_s: float = 0.05,
) -> dict[str, Any]:
    """Backfill session 1m for symbols that lack OR coverage."""
    import asyncio

    day = session_date or datetime.now(tz=IST).date()
    start = combine_ist(day, time(9, 15))
    end = combine_ist(day, time(15, 30))
    ingestion = MarketDataIngestionService(provider, instrument_repo, candle_repo)

    attempted = 0
    saved_total = 0
    skipped = 0
    errors: list[str] = []

    for sym in symbols:
        attempted += 1
        try:
            inst = await instrument_repo.get_by_symbol(sym)
            if inst is None:
                # Still try ingest — get_or_create inside ingest
                pass
            else:
                existing = await candle_repo.get_range(inst.id, "1m", start, end)
                if existing and len(existing) >= 5:
                    skipped += 1
                    continue
            _fetched, persisted = await ingestion.ingest(sym, "1m", start, end)
            saved_total += int(persisted or 0)
            if persisted == 0:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sym}:{exc}")
        if pause_s > 0:
            await asyncio.sleep(pause_s)

    return {
        "attempted": attempted,
        "saved": saved_total,
        "skipped": skipped,
        "errors": errors[:20],
        "session_date": day.isoformat(),
    }


__all__ = ["ensure_1m_for_symbols"]
