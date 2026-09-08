"""Unit tests for intraday ORB practice exit rules."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.intraday.practice import IntradayPracticeTrade, evaluate_orb_exit

IST = ZoneInfo("Asia/Kolkata")


def test_long_stop_hits_before_eod():
    now = datetime(2026, 9, 7, 11, 0, tzinfo=IST)
    decision = evaluate_orb_exit(
        direction="LONG",
        mark=Decimal("99"),
        stop_loss=Decimal("100"),
        now_ist=now,
    )
    assert decision.should_exit
    assert decision.reason == "STOP"


def test_eod_flatten_after_1510():
    now = datetime(2026, 9, 7, 15, 11, tzinfo=IST)
    decision = evaluate_orb_exit(
        direction="LONG",
        mark=Decimal("110"),
        stop_loss=Decimal("100"),
        now_ist=now,
    )
    assert decision.should_exit
    assert decision.reason == "EOD_EXIT"
    assert decision.exit_price == Decimal("110")


def test_no_exit_mid_session():
    now = datetime(2026, 9, 7, 12, 0, tzinfo=IST)
    decision = evaluate_orb_exit(
        direction="LONG",
        mark=Decimal("105"),
        stop_loss=Decimal("100"),
        now_ist=now,
    )
    assert not decision.should_exit


def test_practice_trade_apply_mark_stop():
    trade = IntradayPracticeTrade(
        symbol="AAA",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("98"),
        quantity=10,
        session_date=datetime(2026, 9, 7).date(),
        session_id="s1",
        opened_at=datetime(2026, 9, 7, 10, 0, tzinfo=IST),
    )
    trade.apply_mark(Decimal("97"), now=datetime(2026, 9, 7, 11, 0, tzinfo=IST))
    assert trade.status == "CLOSED"
    assert trade.exit_reason == "STOP"
