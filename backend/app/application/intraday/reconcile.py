"""Paper practice restart reconcile — compare OPEN practice rows to session fills."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def reconcile_practice_vs_session(
    *,
    practice_trades: list[dict[str, Any]],
    session_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return mismatches and whether trading should halt for the session.

    Paper V1: halt when an OPEN practice symbol is missing from model fills,
    or quantity/entry drift beyond 1 tick vs the session fill plan.
    """
    fills = {
        str(f.get("symbol", "")).upper(): f
        for f in (session_payload.get("fills") or [])
        if f.get("symbol")
    }
    issues: list[dict[str, Any]] = []
    open_rows = [t for t in practice_trades if str(t.get("status") or "").upper() == "OPEN"]

    for trade in open_rows:
        sym = str(trade.get("symbol") or "").upper()
        fill = fills.get(sym)
        if fill is None:
            issues.append(
                {
                    "symbol": sym,
                    "code": "ORPHAN_OPEN",
                    "detail": "OPEN practice trade has no matching session fill",
                }
            )
            continue
        try:
            entry = Decimal(str(trade.get("entry_price")))
            fill_entry = Decimal(str(fill.get("entry")))
            qty = int(trade.get("quantity") or 0)
            fill_qty = int(fill.get("quantity") or 0)
        except Exception:  # noqa: BLE001
            issues.append({"symbol": sym, "code": "PARSE_ERROR", "detail": "bad entry/qty"})
            continue
        if qty != fill_qty:
            issues.append(
                {
                    "symbol": sym,
                    "code": "QTY_MISMATCH",
                    "detail": f"practice={qty} model={fill_qty}",
                }
            )
        if abs(entry - fill_entry) > Decimal("0.05"):
            issues.append(
                {
                    "symbol": sym,
                    "code": "ENTRY_DRIFT",
                    "detail": f"practice={entry} model={fill_entry}",
                }
            )

    # Model fill without practice open/closed — informational only
    practice_syms = {str(t.get("symbol") or "").upper() for t in practice_trades}
    for sym, fill in fills.items():
        if sym not in practice_syms:
            issues.append(
                {
                    "symbol": sym,
                    "code": "MISSING_PRACTICE",
                    "detail": "session fill not seeded into practice",
                }
            )

    halt_codes = {"ORPHAN_OPEN", "QTY_MISMATCH", "ENTRY_DRIFT", "PARSE_ERROR"}
    trading_halted = any(i["code"] in halt_codes for i in issues)
    return {
        "ok": not trading_halted,
        "trading_halted": trading_halted,
        "issue_count": len(issues),
        "issues": issues,
        "claim": (
            "Practice reconcile vs session fills — halt on orphan/qty/entry drift "
            "(paper V1; no broker OMS yet)."
        ),
    }


__all__ = ["reconcile_practice_vs_session"]
