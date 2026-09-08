"""IST session helpers for ORB V1."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


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


def iter_session_dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if is_weekday(cur):
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
    "iter_session_dates",
    "minute_bar_opens",
]
