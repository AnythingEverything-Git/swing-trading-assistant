"""Multi-day intraday ORB backtest (CONFIG_V1) with friction + walk-forward split.

Not a full certification gate — use for smoke / cost stress / IS vs OOS draft.

Examples (from backend/):

    python scripts/run_intraday_backtest.py --source demo --start 2026-09-01 --end 2026-09-07
    python scripts/run_intraday_backtest.py --start 2026-09-01 --end 2026-09-07 --oos-start 2026-09-05
    python scripts/run_intraday_backtest.py --start 2026-09-01 --end 2026-09-07 --holdout-frac 0.3 --cost-mult 2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.intraday.backtest_report import entry_time_bucket, split_walk_forward, summarize_day_rows
from app.application.intraday.session_service import run_intraday_session
from app.application.market_data.query_service import MarketDataQueryService
from app.core.config import get_settings
from app.domain.intraday.asset_class import sector_map
from app.domain.intraday.session_calendar import is_weekday
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.intraday_session_repository import (
    IntradaySessionRepository,
)
from app.infrastructure.database.session import create_engine, create_sessionmaker


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def _run_backtest(
    *,
    start: date,
    end: date,
    source: str,
    symbols: list[str] | None,
    equity: Decimal,
    persist: bool,
    cost_mult: Decimal = Decimal("1"),
    oos_start: date | None = None,
    holdout_frac: float | None = None,
) -> dict:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    days: list[date] = []
    cur = start
    while cur <= end:
        if is_weekday(cur):
            days.append(cur)
        cur += timedelta(days=1)

    is_days, oos_days = split_walk_forward(days, oos_start=oos_start, holdout_frac=holdout_frac)

    slip_bps = Decimal("2")
    tick = Decimal("0.05")
    day_rows: list[dict] = []

    try:
        async with sessionmaker() as session:
            query = MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
            repo = IntradaySessionRepository(session) if persist else None
            for day in days:
                _sid, report, meta = await run_intraday_session(
                    session_date=day,
                    symbols=symbols,
                    equity=equity,
                    source=source,  # type: ignore[arg-type]
                    query=query if source == "persisted" else None,
                    session_repo=repo,
                )
                if persist:
                    await session.commit()

                day_pnl = sum((t.pnl for t in report.closed_trades), Decimal("0"))
                day_cost = Decimal("0")
                for fill in report.fills:
                    per_share = max(tick, fill.entry * slip_bps / Decimal("10000"))
                    day_cost += per_share * Decimal(2) * Decimal(fill.quantity)
                day_cost *= cost_mult

                winners = sum(1 for t in report.closed_trades if t.pnl > 0)
                losers = sum(1 for t in report.closed_trades if t.pnl < 0)
                symbol_pnl: dict[str, str] = {}
                symbol_sectors: dict[str, str] = {}
                sectors = sector_map()
                entry_time_buckets: dict[str, int] = {}
                mfe_sum = Decimal("0")
                mae_sum = Decimal("0")
                givebacks: list[str] = []
                for t in report.closed_trades:
                    sym = t.fill.symbol
                    symbol_pnl[sym] = str(Decimal(symbol_pnl.get(sym, "0")) + t.pnl)
                    symbol_sectors[sym] = sectors.get(sym, "UNKNOWN")
                    bucket = entry_time_bucket(t.fill.trigger_bar_open.isoformat())
                    entry_time_buckets[bucket] = entry_time_buckets.get(bucket, 0) + 1
                    mfe_sum += t.mfe
                    mae_sum += t.mae
                    if t.giveback is not None:
                        givebacks.append(str(t.giveback))

                reason_counts: dict[str, int] = {}
                for r in report.symbol_results:
                    reason_counts[r.reason] = reason_counts.get(r.reason, 0) + 1

                coverage_pct = (
                    round(100.0 * report.coverage_eligible / report.coverage_total, 2)
                    if report.coverage_total
                    else 0.0
                )
                bucket = "oos" if day in oos_days else "is"
                day_rows.append(
                    {
                        "session_date": day.isoformat(),
                        "bucket": bucket,
                        "fills": len(report.fills),
                        "closed": len(report.closed_trades),
                        "winners": winners,
                        "losers": losers,
                        "pnl": str(day_pnl),
                        "est_friction": str(day_cost),
                        "pnl_after_friction": str(day_pnl - day_cost),
                        "eligible": report.coverage_eligible,
                        "total": report.coverage_total,
                        "coverage_pct": coverage_pct,
                        "reason_counts": reason_counts,
                        "symbol_pnl": symbol_pnl,
                        "symbol_sectors": symbol_sectors,
                        "entry_time_buckets": entry_time_buckets,
                        "mfe_sum": str(mfe_sum),
                        "mae_sum": str(mae_sum),
                        "givebacks": givebacks,
                        "data_source": meta.get("data_source"),
                    }
                )
    finally:
        await engine.dispose()

    is_rows = [d for d in day_rows if d["bucket"] == "is"]
    oos_rows = [d for d in day_rows if d["bucket"] == "oos"]
    overall = summarize_day_rows(day_rows, cost_mult=cost_mult)
    is_summary = summarize_day_rows(is_rows, cost_mult=cost_mult)
    oos_summary = summarize_day_rows(oos_rows, cost_mult=cost_mult)

    go_no_go_notes = []
    if overall["flags"].get("thin_sample_warn"):
        go_no_go_notes.append("Thin sample (<20 closed trades) — do not certify.")
    if overall["flags"].get("concentration_warn"):
        go_no_go_notes.append("PnL concentrated in ≤3 symbols — automatic rejection risk (§24).")
    if overall["flags"].get("cost_fragile_at_stress"):
        go_no_go_notes.append("Sign flips after friction stress — cost fragile.")
    if oos_rows and Decimal(str(oos_summary["net_pnl_after_friction"])) < 0 and Decimal(str(is_summary["net_pnl_after_friction"])) > 0:
        go_no_go_notes.append("OOS collapses vs in-sample — do not mutate V1; design V2 if needed.")
    if not go_no_go_notes:
        go_no_go_notes.append("No automatic red flags in this scaffold — still not certified without PIT universe + MFE/MAE + multi-year data.")

    return {
        "strategy_id": "NSE_STOCKS_ETF_ORB_RVOL_5M_V1",
        "config_hash": "CONFIG_V1",
        "source": source,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "oos_start": oos_start.isoformat() if oos_start else None,
        "holdout_frac": holdout_frac,
        "cost_stress_mult": str(cost_mult),
        "overall": overall,
        "in_sample": is_summary,
        "oos": oos_summary,
        "go_no_go_notes": go_no_go_notes,
        "days": day_rows,
        "note": "Scaffold only — not V1 certification. See docs/INTRADAY_CERTIFICATION_V1.md.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Intraday ORB multi-day backtest scaffold")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--source", choices=("demo", "persisted"), default="demo")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols")
    parser.add_argument("--equity", type=Decimal, default=Decimal("1000000"))
    parser.add_argument("--persist", action="store_true", help="Write each day to intraday_sessions")
    parser.add_argument(
        "--cost-mult",
        type=Decimal,
        default=Decimal("1"),
        help="Stress multiplier on estimated round-trip friction (e.g. 2 = double costs)",
    )
    parser.add_argument("--oos-start", type=date.fromisoformat, default=None, help="First OOS session date")
    parser.add_argument(
        "--holdout-frac",
        type=float,
        default=None,
        help="Hold out last fraction of sessions as OOS (e.g. 0.3)",
    )
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args()
    if args.start > args.end:
        raise SystemExit("--start must be <= --end")
    if args.oos_start is not None and args.holdout_frac is not None:
        raise SystemExit("Use only one of --oos-start or --holdout-frac")
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    report = _run_async(
        _run_backtest(
            start=args.start,
            end=args.end,
            source=args.source,
            symbols=symbols,
            equity=args.equity,
            persist=args.persist,
            cost_mult=args.cost_mult,
            oos_start=args.oos_start,
            holdout_frac=args.holdout_frac,
        )
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
