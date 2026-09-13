"""Product-facing EXECUTE / WATCH / REJECT decisions for ORB V1.

Derived only from frozen SideOutcome / morning-board size_status.
Does not change CONFIG_V1 numerics or screen/rank rules.
"""
from __future__ import annotations

from typing import Literal

Decision = Literal["EXECUTE", "WATCH", "REJECT"]

_EXECUTE_REASONS = frozenset({"TRADED"})

_WATCH_REASONS = frozenset(
    {
        "RANKED_ARMED",
        "BREAKOUT_NOT_TRIGGERED",
        "ENTRY_CUTOFF",
    }
)

_WATCH_SIZE_STATUSES = frozenset(
    {
        "PENDING",
        "PORTFOLIO_RISK_LIMIT",
        "ZERO_QTY",
    }
)

_EXECUTE_SIZE_STATUSES = frozenset({"SIZED"})

_REJECT_ELIGIBILITY = frozenset(
    {
        "SURVEILLANCE_BLOCKED",
        "CORPORATE_ACTION_BLOCK",
    }
)

_WATCH_ELIGIBILITY = frozenset(
    {
        "ADV_OK",
        "WATCHLIST",
        "LOW_ADV",
    }
)


def decision_from_reason(reason: str | None) -> Decision:
    """Map a session/symbol SideOutcome reason to EXECUTE | WATCH | REJECT."""
    code = str(reason or "").strip().upper()
    if not code:
        return "REJECT"
    if code in _EXECUTE_REASONS:
        return "EXECUTE"
    if code in _WATCH_REASONS:
        return "WATCH"
    return "REJECT"


def decision_from_board_row(
    *,
    status: str | None = None,
    size_status: str | None = None,
    reason: str | None = None,
) -> Decision:
    """Morning-board row decision.

    EXECUTE — capital allocated (SIZED); ready to fill on 1m breakout.
    WATCH — ranked / pending slot / pre-OR eligibility / waiting trigger.
    REJECT — screen fail, risk invalid, surveillance / CA block.
    """
    size = str(size_status or "").strip().upper()
    st = str(status or "").strip().upper()

    if size in _EXECUTE_SIZE_STATUSES:
        return "EXECUTE"
    if size in _WATCH_SIZE_STATUSES:
        return "WATCH"
    if size in {"RISK_INVALID", "ORDER_REJECTED"} or size.endswith("_LOCK"):
        return "REJECT"

    if st == "RANKED":
        return "WATCH"
    if st in _REJECT_ELIGIBILITY:
        return "REJECT"
    if st in _WATCH_ELIGIBILITY:
        return "WATCH"

    if reason:
        return decision_from_reason(reason)

    return "REJECT"


def decision_label(decision: Decision) -> str:
    return {
        "EXECUTE": "Execute",
        "WATCH": "Watch",
        "REJECT": "Reject",
    }[decision]


def decision_hint(decision: Decision) -> str:
    return {
        "EXECUTE": "Sized within capital — take the 1m breakout when it prints.",
        "WATCH": "Valid / ranked setup waiting on trigger, cutoff, or a free portfolio slot.",
        "REJECT": "Rules blocked this name for today — see reason code.",
    }[decision]


def count_decisions(rows: list[dict]) -> dict[str, int]:
    out = {"EXECUTE": 0, "WATCH": 0, "REJECT": 0}
    for row in rows:
        key = str(row.get("decision") or "REJECT").upper()
        if key not in out:
            key = "REJECT"
        out[key] += 1
    return out


__all__ = [
    "Decision",
    "decision_from_reason",
    "decision_from_board_row",
    "decision_label",
    "decision_hint",
    "count_decisions",
]
