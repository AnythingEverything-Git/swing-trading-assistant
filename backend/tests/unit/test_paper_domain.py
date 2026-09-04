"""Exhaustive unit tests for paper MTM and stop/target exits."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.paper import PaperTrade, evaluate_exit, realized_pnl, unrealized_pnl


def test_long_unrealized_and_realized():
    assert unrealized_pnl(direction="LONG", entry=Decimal("100"), mark=Decimal("110"), quantity=2) == Decimal("20")
    assert realized_pnl(direction="LONG", entry=Decimal("100"), exit_price=Decimal("90"), quantity=2) == Decimal("-20")


def test_short_unrealized_and_realized():
    assert unrealized_pnl(direction="SHORT", entry=Decimal("100"), mark=Decimal("90"), quantity=2) == Decimal("20")
    assert realized_pnl(direction="SHORT", entry=Decimal("100"), exit_price=Decimal("110"), quantity=2) == Decimal("-20")


def test_long_exit_stop_before_target_when_both_hit():
    decision = evaluate_exit(
        direction="LONG",
        mark=Decimal("50"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
    )
    # mark below stop; target also "hit" in gap sense only if mark >= target — here only stop
    assert decision.should_exit is True
    assert decision.reason == "STOP_LOSS"
    assert decision.exit_price == Decimal("95")


def test_long_both_hit_prefers_stop():
    # Pathological gap: mark somehow satisfies both inequalities only if stop > target (invalid).
    # Conservative rule: check stop first.
    decision = evaluate_exit(
        direction="LONG",
        mark=Decimal("100"),
        stop_loss=Decimal("100"),
        target=Decimal("100"),
    )
    assert decision.reason == "STOP_LOSS"


def test_long_target_exit():
    decision = evaluate_exit(
        direction="LONG",
        mark=Decimal("120"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
    )
    assert decision.reason == "TARGET"
    assert decision.exit_price == Decimal("110")


def test_short_stop_and_target():
    stop = evaluate_exit(
        direction="SHORT",
        mark=Decimal("105"),
        stop_loss=Decimal("102"),
        target=Decimal("90"),
    )
    assert stop.reason == "STOP_LOSS"
    target = evaluate_exit(
        direction="SHORT",
        mark=Decimal("88"),
        stop_loss=Decimal("102"),
        target=Decimal("90"),
    )
    assert target.reason == "TARGET"


def test_short_both_hit_prefers_stop():
    decision = evaluate_exit(
        direction="SHORT",
        mark=Decimal("100"),
        stop_loss=Decimal("100"),
        target=Decimal("100"),
    )
    assert decision.reason == "STOP_LOSS"


def test_no_exit_when_inside_range():
    decision = evaluate_exit(
        direction="LONG",
        mark=Decimal("101"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
    )
    assert decision.should_exit is False


def test_paper_trade_apply_mark_updates_unrealized():
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="OPEN",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    decision = trade.apply_mark(Decimal("103"))
    assert decision.should_exit is False
    assert trade.unrealized_pnl == Decimal("30")
    assert trade.last_mark_price == Decimal("103")
    assert trade.status == "OPEN"


def test_paper_trade_apply_mark_closes_on_stop():
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="OPEN",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    decision = trade.apply_mark(Decimal("94"))
    assert decision.reason == "STOP_LOSS"
    assert trade.status == "CLOSED"
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.exit_price == Decimal("95")
    assert trade.realized_pnl == Decimal("-50")
    assert trade.unrealized_pnl == Decimal("0")


def test_paper_trade_short_closes_on_target():
    trade = PaperTrade(
        symbol="TCS",
        direction="SHORT",
        entry_price=Decimal("100"),
        stop_loss=Decimal("105"),
        target=Decimal("90"),
        quantity=5,
        risk_amount=Decimal("25"),
        status="OPEN",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    trade.apply_mark(Decimal("89"))
    assert trade.status == "CLOSED"
    assert trade.exit_reason == "TARGET"
    assert trade.realized_pnl == Decimal("50")


def test_paper_trade_manual_close():
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=2,
        risk_amount=Decimal("10"),
        status="OPEN",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    trade.close_manual(Decimal("104"))
    assert trade.status == "CLOSED"
    assert trade.exit_reason == "MANUAL"
    assert trade.realized_pnl == Decimal("8")


def test_paper_trade_cancel_pending():
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=2,
        risk_amount=Decimal("10"),
        status="PENDING",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    trade.close_manual(Decimal("0"))
    assert trade.status == "CLOSED"
    assert trade.exit_reason == "CANCELLED"
    assert trade.exit_price is None
    assert trade.realized_pnl == Decimal("0")


def test_entry_reached_helpers():
    from app.domain.paper import entry_reached

    assert entry_reached(direction="LONG", mark=Decimal("100"), entry=Decimal("100"))
    assert not entry_reached(direction="LONG", mark=Decimal("99.99"), entry=Decimal("100"))
    assert entry_reached(direction="SHORT", mark=Decimal("100"), entry=Decimal("100"))
    assert not entry_reached(direction="SHORT", mark=Decimal("100.01"), entry=Decimal("100"))


def test_paper_trade_rejects_bad_geometry():
    with pytest.raises(ValueError):
        PaperTrade(
            symbol="X",
            direction="LONG",
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            target=Decimal("110"),
            quantity=1,
            risk_amount=None,
            status="OPEN",
            opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
