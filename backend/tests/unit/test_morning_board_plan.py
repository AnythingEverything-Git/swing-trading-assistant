"""Trading calendar + morning board plan fields."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.domain.intraday.breakout import planned_entry_price, planned_target_price, stop_price
from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1
from app.domain.intraday.session_calendar import (
    IST,
    default_session_date,
    is_trading_day,
    last_trading_day,
)
from app.domain.intraday.types import OpeningRange


def test_weekends_are_not_trading_days():
    assert not is_trading_day(date(2026, 9, 12))  # Saturday
    assert not is_trading_day(date(2026, 9, 13))  # Sunday
    assert is_trading_day(date(2026, 9, 11))  # Friday


def test_nse_holiday_not_trading():
    assert not is_trading_day(date(2026, 1, 26))  # Republic Day
    assert last_trading_day(date(2026, 1, 26)) == date(2026, 1, 23)


def test_default_session_date_skips_weekend():
    saturday = datetime(2026, 9, 12, 10, 0, tzinfo=IST)
    assert default_session_date(saturday) == date(2026, 9, 11)


def test_planned_entry_long_above_or_high():
    orng = OpeningRange(
        symbol="TEST",
        session_date=date(2026, 9, 11),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=1000,
        bar_open=datetime(2026, 9, 11, 9, 15, tzinfo=IST),
    )
    entry = planned_entry_price(orng, "LONG", Decimal("0.05"), DEFAULT_CONFIG_V1)
    assert entry > orng.high


def test_stop_never_non_positive_when_atr_wide():
    entry = Decimal("100.05")
    stop = stop_price(entry, "LONG", Decimal("150"), Decimal("0.05"))
    assert stop > 0
    assert stop < entry


def test_planned_target_is_one_r():
    entry = Decimal("100.00")
    dist = Decimal("2.00")
    stop = stop_price(entry, "LONG", dist, Decimal("0.05"))
    target = planned_target_price(entry, "LONG", dist, Decimal("0.05"))
    assert stop < entry < target
    assert abs((entry - stop) - (target - entry)) <= Decimal("0.05")

    short_stop = stop_price(entry, "SHORT", dist, Decimal("0.05"))
    short_target = planned_target_price(entry, "SHORT", dist, Decimal("0.05"))
    assert short_target < entry < short_stop
    assert abs((short_stop - entry) - (entry - short_target)) <= Decimal("0.05")


@pytest.mark.asyncio
async def test_morning_board_rejects_weekend():
    from app.application.intraday.morning_board_service import build_morning_board

    with pytest.raises(ValueError, match="trading day"):
        await build_morning_board(session_date=date(2026, 9, 12), source="demo", universe="DEMO_SAMPLE")


@pytest.mark.asyncio
async def test_morning_board_plan_columns_and_qty():
    from app.application.intraday.morning_board_service import build_morning_board

    board = await build_morning_board(
        session_date=date(2026, 9, 11),
        source="demo",
        universe="DEMO_SAMPLE",
        equity=Decimal("1000000"),
        now=datetime(2026, 9, 11, 10, 0, tzinfo=IST),
    )
    assert board["phase"] in ("LIVE_SCREEN", "HISTORICAL")
    rows = board["ranked_stocks"]
    assert rows, "demo sample should produce ranked stocks"
    row = rows[0]
    assert row.get("entry")
    assert row.get("stop")
    assert Decimal(str(row["stop"])) > 0
    assert row.get("target")
    assert Decimal(str(row["target"])) > 0
    assert row.get("target_label") == "1R"
    entry = Decimal(str(row["entry"]))
    stop = Decimal(str(row["stop"]))
    target = Decimal(str(row["target"]))
    if row.get("direction") == "LONG":
        assert stop < entry < target
    else:
        assert target < entry < stop
    assert "reason" in row
    assert row.get("decision") in {"EXECUTE", "WATCH", "REJECT"}
    sized = [r for r in rows if (r.get("quantity") or 0) > 0]
    assert len(sized) <= 3
    assert all(r.get("status") == "RANKED" for r in rows)
    assert all(r.get("decision") == "EXECUTE" for r in sized)
