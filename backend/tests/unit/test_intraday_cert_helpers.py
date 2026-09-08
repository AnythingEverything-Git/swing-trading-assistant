"""Tests for eligibility PIT loaders and walk-forward split."""
from __future__ import annotations

from datetime import date

from app.application.intraday.backtest_report import split_walk_forward
from app.application.intraday.reconcile import reconcile_practice_vs_session
from app.domain.intraday.eligibility import (
    clear_eligibility_caches,
    is_corporate_action_blocked,
    is_short_allowed,
    is_surveillance_blocked,
)


def test_short_allow_denylist_and_allowlist():
    clear_eligibility_caches()
    assert is_short_allowed("RELIANCE") is True
    assert is_short_allowed("NIFTYBEES") is False
    # Allowlist mode: obscure symbols not listed are not shortable
    assert is_short_allowed("ZZZNOSHORT") is False


def test_surveillance_dated_entry():
    clear_eligibility_caches()
    assert is_surveillance_blocked("YESBANK", session_date=date(2026, 9, 8)) is True
    assert is_surveillance_blocked("RELIANCE", session_date=date(2026, 9, 8)) is False


def test_corporate_action_ex_date():
    clear_eligibility_caches()
    assert is_corporate_action_blocked("INFY", date(2026, 9, 7)) is True
    assert is_corporate_action_blocked("INFY", date(2026, 9, 8)) is False


def test_reconcile_orphan_halts():
    result = reconcile_practice_vs_session(
        practice_trades=[
            {
                "symbol": "AAA",
                "status": "OPEN",
                "entry_price": "100",
                "quantity": 10,
            }
        ],
        session_payload={"fills": []},
    )
    assert result["trading_halted"] is True
    assert any(i["code"] == "ORPHAN_OPEN" for i in result["issues"])


def test_split_oos_start():
    days = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)]
    is_days, oos = split_walk_forward(days, oos_start=date(2026, 9, 3))
    assert is_days == [date(2026, 9, 1), date(2026, 9, 2)]
    assert oos == [date(2026, 9, 3), date(2026, 9, 4)]


def test_split_holdout_frac():
    days = [date(2026, 9, d) for d in range(1, 11)]
    is_days, oos = split_walk_forward(days, holdout_frac=0.3)
    assert len(is_days) + len(oos) == 10
    assert len(oos) >= 1
    assert is_days[-1] < oos[0]


def test_morning_universe_is_full_nse():
    from app.domain.intraday.asset_class import morning_universe_symbols

    ordered, classes = morning_universe_symbols()
    assert len(ordered) > 1000
    assert sum(1 for s in ordered if classes[s] == "ETF") >= 50
