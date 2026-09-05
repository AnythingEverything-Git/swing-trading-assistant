"""Grounded backtest interpreter — metrics JSON is source of truth."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.application.narrative.grounded_narrator import GroundedNarrator, GroundedTextResult

_MIN_TRADES = 5


def _template_summary(metrics: dict[str, Any]) -> str:
    total = int(metrics.get("total_trades") or 0)
    if total < _MIN_TRADES:
        return (
            f"Only {total} completed trade(s) in this window — too few for a reliable read. "
            "Treat win rate and average R as anecdotal until the sample grows."
        )
    win_rate = metrics.get("win_rate")
    avg_r = metrics.get("average_r")
    max_dd = metrics.get("maximum_drawdown")
    return (
        f"Sample of {total} trades: win rate {win_rate}, average R {avg_r}, "
        f"max drawdown {max_dd}. Past results are not a live edge guarantee."
    )


def metrics_as_dict(metrics: Any) -> dict[str, Any]:
    if isinstance(metrics, dict):
        return metrics
    return {
        "total_trades": getattr(metrics, "total_trades", 0),
        "winning_trades": getattr(metrics, "winning_trades", 0),
        "losing_trades": getattr(metrics, "losing_trades", 0),
        "win_rate": getattr(metrics, "win_rate", Decimal("0")),
        "total_pnl": getattr(metrics, "total_pnl", Decimal("0")),
        "average_pnl": getattr(metrics, "average_pnl", Decimal("0")),
        "total_r": getattr(metrics, "total_r", Decimal("0")),
        "average_r": getattr(metrics, "average_r", Decimal("0")),
        "maximum_drawdown": getattr(metrics, "maximum_drawdown", Decimal("0")),
    }


async def interpret_backtest(
    narrator: GroundedNarrator | None,
    *,
    metrics: dict[str, Any],
    symbol: str | None = None,
) -> GroundedTextResult:
    facts = {
        "symbol": symbol,
        "total_trades": metrics.get("total_trades"),
        "winning_trades": metrics.get("winning_trades"),
        "losing_trades": metrics.get("losing_trades"),
        "win_rate": str(metrics.get("win_rate")),
        "average_r": str(metrics.get("average_r")),
        "total_r": str(metrics.get("total_r")),
        "maximum_drawdown": str(metrics.get("maximum_drawdown")),
        "total_pnl": str(metrics.get("total_pnl")),
        "average_pnl": str(metrics.get("average_pnl")),
        "min_trades_for_summary": _MIN_TRADES,
    }
    fallback = _template_summary(metrics)
    total = int(metrics.get("total_trades") or 0)
    if total < _MIN_TRADES:
        return GroundedTextResult(
            text=fallback, provider="template", grounded=True, detail="too_few_trades"
        )
    if narrator is None or not narrator.enabled:
        return GroundedTextResult(
            text=fallback, provider="template", grounded=True, detail="llm_disabled"
        )
    return await narrator.rephrase_text(
        kind="backtest_summary",
        source_text=fallback,
        facts=facts,
        instruction=(
            "Write 2 short sentences interpreting these backtest metrics. "
            "Call out sample size, win rate, average R, and max drawdown. "
            "Refuse to overclaim; do not invent numbers."
        ),
    )


__all__ = ["interpret_backtest", "metrics_as_dict"]
