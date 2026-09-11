"""Helpers to hold/release the in-process market-data refresh mutex."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def acquire_refresh_mutex(app_state: Any) -> bool:
    """Return True if mutex acquired; False if already held."""
    if getattr(app_state, "refresh_running", False):
        return False
    app_state.refresh_running = True
    app_state.refresh_running_since = datetime.now(timezone.utc)
    return True


def mark_refresh_mutex_held(app_state: Any) -> None:
    """Mark mutex held (caller already checked it was free)."""
    app_state.refresh_running = True
    app_state.refresh_running_since = datetime.now(timezone.utc)


def release_refresh_mutex(app_state: Any) -> None:
    app_state.refresh_running = False
    app_state.refresh_running_since = None


__all__ = ["acquire_refresh_mutex", "mark_refresh_mutex_held", "release_refresh_mutex"]
