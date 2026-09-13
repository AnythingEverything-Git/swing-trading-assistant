"""IST session helpers for ORB V1."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_HOLIDAYS_PATH = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "universe" / "data" / "nse_holidays.json"
)


@lru_cache(maxsize=1)
def nse_holidays() -> frozenset[date]:
    """Full-day NSE CM holidays (and Muhurat days treated as non-ORB)."""
    try:
        raw = json.loads(_HOLIDAYS_PATH.read_text(encoding="utf-8"))
        return frozenset(date.fromisoformat(str(x)) for x in raw.get("holidays") or [])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return frozenset()


def to_ist(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return ts.astimezone(IST)


def session_day(ts: datetime) -> date:
    return to_ist(ts).date()


def combine_ist(day: date, clock: time) -> datetime:
    return datetime(day.year, day.month, day.day, clock.hour, clock.minute, clock.second, tzinfo=IST)


def is_weekday(day: date) -> bool:
    return day.weekday() < 5


def is_nse_holiday(day: date) -> bool:
    return day in nse_holidays()


def is_trading_day(day: date) -> bool:
    """Weekday and not on the NSE holiday / Muhurat list."""
    return is_weekday(day) and not is_nse_holiday(day)


def last_trading_day(on_or_before: date | None = None) -> date:
    """Most recent trading day on or before the given calendar date (IST today if omitted)."""
    cur = on_or_before or datetime.now(tz=IST).date()
    for _ in range(370):
        if is_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    return cur


def default_session_date(now: datetime | None = None) -> date:
    clock = now or datetime.now(tz=IST)
    return last_trading_day(clock.astimezone(IST).date())


def iter_session_dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def minute_bar_opens(day: date, start: time, end_exclusive: time) -> list[datetime]:
    """Return 1m bar open times in [start, end_exclusive)."""
    cur = combine_ist(day, start)
    stop = combine_ist(day, end_exclusive)
    out: list[datetime] = []
    while cur < stop:
        out.append(cur)
        cur += timedelta(minutes=1)
    return out


__all__ = [
    "IST",
    "to_ist",
    "session_day",
    "combine_ist",
    "is_weekday",
    "is_nse_holiday",
    "is_trading_day",
    "last_trading_day",
    "default_session_date",
    "nse_holidays",
    "iter_session_dates",
    "minute_bar_opens",
]
