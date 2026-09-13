"""G2 product decisions: EXECUTE / WATCH / REJECT (derived, no CONFIG_V1 changes)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.domain.intraday.decision import (
    decision_from_board_row,
    decision_from_reason,
)

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("TRADED", "EXECUTE"),
        ("RANKED_ARMED", "WATCH"),
        ("BREAKOUT_NOT_TRIGGERED", "WATCH"),
        ("ENTRY_CUTOFF", "WATCH"),
        ("PORTFOLIO_RISK_LIMIT", "REJECT"),
        ("RISK_INVALID", "REJECT"),
        ("DOJI", "REJECT"),
        ("NOT_IN_TOP_N", "REJECT"),
        ("SURVEILLANCE_BLOCKED", "REJECT"),
    ],
)
def test_decision_from_reason(reason: str, expected: str):
    assert decision_from_reason(reason) == expected


@pytest.mark.parametrize(
    "status,size_status,expected",
    [
        ("RANKED", "SIZED", "EXECUTE"),
        ("RANKED", "PENDING", "WATCH"),
        ("RANKED", "PORTFOLIO_RISK_LIMIT", "WATCH"),
        ("RANKED", "ZERO_QTY", "WATCH"),
        ("RANKED", "RISK_INVALID", "REJECT"),
        ("RANKED", "DAILY_LOSS_LOCK", "REJECT"),
        ("ADV_OK", None, "WATCH"),
        ("SURVEILLANCE_BLOCKED", None, "REJECT"),
        ("CORPORATE_ACTION_BLOCK", None, "REJECT"),
    ],
)
def test_decision_from_board_row(status: str, size_status: str | None, expected: str):
    assert decision_from_board_row(status=status, size_status=size_status) == expected


@pytest.mark.asyncio
async def test_morning_board_includes_decision():
    from app.application.intraday.morning_board_service import build_morning_board

    board = await build_morning_board(
        session_date=date(2026, 9, 11),
        source="demo",
        universe="DEMO_SAMPLE",
        equity=Decimal("1000000"),
        now=datetime(2026, 9, 11, 10, 0, tzinfo=IST),
    )
    rows = board["ranked_stocks"]
    assert rows
    assert "decision_counts" in board
    for row in rows:
        assert row.get("decision") in {"EXECUTE", "WATCH", "REJECT"}
    assert sum(board["decision_counts"].values()) >= len(rows)
