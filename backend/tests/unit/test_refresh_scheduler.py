"""Unit tests for in-app market-data refresh schedule helpers."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.application.market_data.refresh_scheduler import (
    IST,
    next_weekday_fire,
    parse_hhmm,
    scheduler_should_run,
    utc_today_end,
)


def test_parse_hhmm_valid():
    assert parse_hhmm("16:15") == (16, 15)
    assert parse_hhmm("08:45") == (8, 45)


def test_parse_hhmm_invalid():
    with pytest.raises(ValueError):
        parse_hhmm("16")
    with pytest.raises(ValueError):
        parse_hhmm("25:00")


def test_next_weekday_fire_same_day_before_time():
    now = datetime(2026, 9, 4, 10, 0, tzinfo=IST)  # Friday
    fire = next_weekday_fire(now, 16, 15)
    assert fire == datetime(2026, 9, 4, 16, 15, tzinfo=IST)


def test_next_weekday_fire_friday_after_time_skips_weekend():
    now = datetime(2026, 9, 4, 17, 0, tzinfo=IST)  # Friday after 16:15
    fire = next_weekday_fire(now, 16, 15)
    assert fire == datetime(2026, 9, 7, 16, 15, tzinfo=IST)  # Monday


def test_next_weekday_fire_saturday_to_monday():
    now = datetime(2026, 9, 5, 12, 0, tzinfo=IST)  # Saturday
    fire = next_weekday_fire(now, 16, 15)
    assert fire == datetime(2026, 9, 7, 16, 15, tzinfo=IST)


def test_utc_today_end():
    now = datetime(2026, 9, 4, 18, 30, tzinfo=IST)
    end = utc_today_end(now=now)
    assert end.tzinfo is not None
    assert end.hour == 0 and end.minute == 0
    # IST evening is still same UTC calendar day (13:00 UTC)
    assert end.date().isoformat() == "2026-09-04"


def test_scheduler_should_run_upstox_enabled():
    settings = SimpleNamespace(
        market_data_refresh_enabled=True,
        market_data_source="upstox",
    )
    assert scheduler_should_run(settings) is True


def test_scheduler_should_run_demo_disabled():
    settings = SimpleNamespace(
        market_data_refresh_enabled=True,
        market_data_source="demo",
    )
    assert scheduler_should_run(settings) is False


def test_scheduler_should_run_explicit_off():
    settings = SimpleNamespace(
        market_data_refresh_enabled=False,
        market_data_source="upstox",
    )
    assert scheduler_should_run(settings) is False
