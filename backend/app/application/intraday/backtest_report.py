"""Helpers for intraday ORB backtest summaries (not full certification)."""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any


def split_walk_forward(
    days: list[date],
    *,
    oos_start: date | None = None,
    holdout_frac: float | None = None,
) -> tuple[list[date], list[date]]:
    """Split session days into in-sample vs OOS/holdout."""
    if not days:
        return [], []
    if oos_start is not None:
        return [d for d in days if d < oos_start], [d for d in days if d >= oos_start]
    if holdout_frac is not None:
        frac = max(0.0, min(0.9, float(holdout_frac)))
        if frac <= 0:
            return days, []
        cut = max(1, int(round(len(days) * (1.0 - frac))))
        cut = min(cut, len(days) - 1) if len(days) > 1 else len(days)
        return days[:cut], days[cut:]
    return days, []


def entry_time_bucket(entry_iso: str | None) -> str:
    """Bucket entry clock for reporting (IST wall time expected)."""
    if not entry_iso:
        return "unknown"
    try:
        # Accept ...T09:45:00+05:30 or ...T09:45:00
        time_part = entry_iso.split("T", 1)[1][:5]
        hour, minute = [int(x) for x in time_part.split(":")]
    except (IndexError, ValueError):
        return "unknown"
    mins = hour * 60 + minute
    if mins < 9 * 60 + 20:
        return "pre_or"
    if mins < 10 * 60:
        return "09:20-10:00"
    if mins < 11 * 60:
        return "10:00-11:00"
    if mins < 12 * 60:
        return "11:00-12:00"
    if mins < 13 * 60:
        return "12:00-13:00"
    if mins < 14 * 60:
        return "13:00-14:00"
    if mins < 14 * 60 + 30:
        return "14:00-14:30"
    return "after_cutoff"


def summarize_day_rows(day_rows: list[dict[str, Any]], *, cost_mult: Decimal) -> dict[str, Any]:
    if not day_rows:
        return {
            "sessions": 0,
            "fills": 0,
            "closed_trades": 0,
            "winners": 0,
            "losers": 0,
            "win_rate": None,
            "net_pnl": "0",
            "est_friction": "0",
            "net_pnl_after_friction": "0",
            "worst_day_pnl": None,
            "best_day_pnl": None,
            "avg_coverage_pct": None,
            "reason_counts": {},
            "entry_time_buckets": {},
            "mfe_sum": "0",
            "mae_sum": "0",
            "avg_giveback_winners": None,
            "flags": {},
        }

    gross = sum((Decimal(d["pnl"]) for d in day_rows), Decimal("0"))
    friction = sum((Decimal(d["est_friction"]) for d in day_rows), Decimal("0"))
    winners = sum(int(d["winners"]) for d in day_rows)
    losers = sum(int(d["losers"]) for d in day_rows)
    closed = winners + losers
    fills = sum(int(d["fills"]) for d in day_rows)
    pnls = [Decimal(d["pnl"]) for d in day_rows]
    cov = [float(d["coverage_pct"]) for d in day_rows if d.get("coverage_pct") is not None]

    reason_counts: Counter[str] = Counter()
    entry_buckets: Counter[str] = Counter()
    mfe_total = Decimal("0")
    mae_total = Decimal("0")
    giveback_vals: list[Decimal] = []
    for d in day_rows:
        for reason, count in (d.get("reason_counts") or {}).items():
            reason_counts[reason] += int(count)
        for bucket, count in (d.get("entry_time_buckets") or {}).items():
            entry_buckets[bucket] += int(count)
        mfe_total += Decimal(str(d.get("mfe_sum") or "0"))
        mae_total += Decimal(str(d.get("mae_sum") or "0"))
        for g in d.get("givebacks") or []:
            giveback_vals.append(Decimal(str(g)))

    by_symbol: Counter[str] = Counter()
    by_sector: Counter[str] = Counter()
    for d in day_rows:
        for sym, pnl in (d.get("symbol_pnl") or {}).items():
            abs_pnl = abs(Decimal(str(pnl)))
            by_symbol[sym] += abs_pnl
            sector = str((d.get("symbol_sectors") or {}).get(sym) or "UNKNOWN")
            by_sector[sector] += abs_pnl
    total_abs = sum(by_symbol.values(), Decimal("0"))
    top3 = sum((v for _, v in by_symbol.most_common(3)), Decimal("0"))
    top3_share = float(top3 / total_abs) if total_abs > 0 else 0.0
    sector_total = sum(by_sector.values(), Decimal("0"))
    top_sector_share = float(by_sector.most_common(1)[0][1] / sector_total) if sector_total > 0 else 0.0

    net_after = gross - friction
    cost_fragile = (gross > 0 and net_after <= 0) or (gross < 0 and net_after >= 0)

    flags = {
        "concentration_top3_symbol_abs_pnl_share": round(top3_share, 4),
        "concentration_warn": top3_share >= 0.6 and closed >= 5,
        "sector_top_share": round(top_sector_share, 4),
        "sector_concentration_warn": top_sector_share >= 0.5 and closed >= 5,
        "cost_fragile_at_stress": cost_fragile,
        "low_coverage_warn": bool(cov) and (sum(cov) / len(cov) < 50.0),
        "thin_sample_warn": closed < 20,
        "high_giveback_warn": bool(giveback_vals) and (sum(giveback_vals) / len(giveback_vals) >= Decimal("0.5")),
    }

    return {
        "sessions": len(day_rows),
        "fills": fills,
        "closed_trades": closed,
        "winners": winners,
        "losers": losers,
        "win_rate": (float(winners) / closed) if closed else None,
        "net_pnl": str(gross),
        "est_friction": str(friction),
        "net_pnl_after_friction": str(net_after),
        "worst_day_pnl": str(min(pnls)),
        "best_day_pnl": str(max(pnls)),
        "avg_coverage_pct": round(sum(cov) / len(cov), 2) if cov else None,
        "reason_counts": dict(reason_counts),
        "entry_time_buckets": dict(entry_buckets),
        "sector_abs_pnl": {k: str(v) for k, v in by_sector.most_common()},
        "mfe_sum": str(mfe_total),
        "mae_sum": str(mae_total),
        "avg_giveback_winners": str(sum(giveback_vals) / len(giveback_vals)) if giveback_vals else None,
        "flags": flags,
    }


__all__ = ["split_walk_forward", "summarize_day_rows", "entry_time_bucket"]
