"""Point-in-time eligibility for ORB V1 (surveillance, short-allow, corporate actions).

File-backed dumps under ``infrastructure/universe/data``:

- ``short_not_permitted.json`` — denylist (always block shorts)
- ``short_allowed.json`` — optional allowlist; if present, shorts only when listed
- ``surveillance_blocked.json`` — ``{"symbols": [...]}`` or dated
  ``{"entries": [{"symbol": "...", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD"|null}]}``
- ``corporate_actions.json`` — ``{"entries": [{"symbol", "ex_date", "type"}]}``
  Blocks the session on ex_date (and optional ``block_sessions`` lookback).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import AbstractSet, Any

_DATA_DIR = Path(__file__).resolve().parents[2] / "infrastructure" / "universe" / "data"
_DEFAULT_SHORT_DENY = frozenset({"NIFTYBEES", "BANKBEES", "GOLDBEES"})


def _read_json(filename: str) -> dict[str, Any] | list[Any] | None:
    path = _DATA_DIR / filename
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return raw


def _symbols_from_list_payload(raw: object, default: frozenset[str]) -> frozenset[str]:
    if raw is None:
        return default
    if isinstance(raw, dict):
        symbols = raw.get("symbols")
    else:
        symbols = raw
    if not isinstance(symbols, list):
        return default
    return frozenset(str(s).strip().upper() for s in symbols if str(s).strip())


@lru_cache(maxsize=1)
def short_not_permitted_symbols() -> frozenset[str]:
    return _symbols_from_list_payload(_read_json("short_not_permitted.json"), _DEFAULT_SHORT_DENY)


@lru_cache(maxsize=1)
def short_allowed_symbols() -> frozenset[str] | None:
    """None = no allowlist (denylist-only mode). Empty frozenset = allow none."""
    raw = _read_json("short_allowed.json")
    if raw is None:
        return None
    return _symbols_from_list_payload(raw, frozenset())


@lru_cache(maxsize=1)
def _surveillance_payload() -> dict[str, Any]:
    raw = _read_json("surveillance_blocked.json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"symbols": raw}
    return {"symbols": []}


@lru_cache(maxsize=1)
def _corporate_actions_payload() -> list[dict[str, Any]]:
    raw = _read_json("corporate_actions.json")
    if isinstance(raw, dict):
        entries = raw.get("entries")
    elif isinstance(raw, list):
        entries = raw
    else:
        entries = None
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for item in entries:
        if isinstance(item, dict) and item.get("symbol") and item.get("ex_date"):
            out.append(item)
    return out


def clear_eligibility_caches() -> None:
    short_not_permitted_symbols.cache_clear()
    short_allowed_symbols.cache_clear()
    _surveillance_payload.cache_clear()
    _corporate_actions_payload.cache_clear()


def surveillance_blocked_symbols(as_of: date | None = None) -> frozenset[str]:
    """Symbols blocked on ``as_of`` (defaults to today for static lists)."""
    payload = _surveillance_payload()
    day = as_of or date.today()
    blocked: set[str] = set()
    static = payload.get("symbols")
    if isinstance(static, list):
        blocked.update(str(s).strip().upper() for s in static if str(s).strip())
    entries = payload.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol") or "").strip().upper()
            if not sym:
                continue
            start_raw = item.get("from") or item.get("as_of")
            end_raw = item.get("to")
            try:
                start = date.fromisoformat(str(start_raw)) if start_raw else date.min
            except ValueError:
                continue
            try:
                end = date.fromisoformat(str(end_raw)) if end_raw else date.max
            except ValueError:
                end = date.max
            if start <= day <= end:
                blocked.add(sym)
    return frozenset(blocked)


def is_surveillance_blocked(
    symbol: str,
    blocked: AbstractSet[str] | None = None,
    *,
    session_date: date | None = None,
) -> bool:
    table = surveillance_blocked_symbols(session_date) if blocked is None else blocked
    return symbol.strip().upper() in table


def is_short_allowed(
    symbol: str,
    denylist: AbstractSet[str] | None = None,
    *,
    allowlist: AbstractSet[str] | None = None,
) -> bool:
    sym = symbol.strip().upper()
    deny = short_not_permitted_symbols() if denylist is None else denylist
    if sym in deny:
        return False
    allow = short_allowed_symbols() if allowlist is None else allowlist
    if allow is not None:
        return sym in allow
    return True


def is_corporate_action_blocked(
    symbol: str,
    session_date: date,
    *,
    block_sessions: int = 1,
) -> bool:
    """True if symbol has an ex-date on session_date or within prior ``block_sessions-1`` weekdays."""
    sym = symbol.strip().upper()
    if block_sessions < 1:
        block_sessions = 1
    window_start = session_date - timedelta(days=block_sessions + 5)
    for item in _corporate_actions_payload():
        if str(item.get("symbol") or "").strip().upper() != sym:
            continue
        try:
            ex = date.fromisoformat(str(item["ex_date"]))
        except (KeyError, ValueError):
            continue
        sessions = int(item.get("block_sessions") or block_sessions)
        # Block on ex_date and the previous ``sessions-1`` calendar weekdays approximation.
        if ex == session_date:
            return True
        if sessions > 1 and window_start <= ex < session_date:
            # Count weekdays between ex and session
            gap = 0
            cur = ex
            while cur < session_date:
                cur += timedelta(days=1)
                if cur.weekday() < 5:
                    gap += 1
                if gap >= sessions:
                    break
            if 0 < gap < sessions:
                return True
    return False


def eligibility_flags(symbol: str, session_date: date) -> dict[str, bool]:
    """Compact flags for screen bundles / morning board."""
    return {
        "surveillance_blocked": is_surveillance_blocked(symbol, session_date=session_date),
        "short_allowed": is_short_allowed(symbol),
        "corporate_action_blocked": is_corporate_action_blocked(symbol, session_date),
    }


# Eager aliases (static snapshot at import — prefer functions for PIT)
SHORT_NOT_PERMITTED_SYMBOLS = short_not_permitted_symbols()
SURVEILLANCE_BLOCKED_SYMBOLS = surveillance_blocked_symbols()


__all__ = [
    "SURVEILLANCE_BLOCKED_SYMBOLS",
    "SHORT_NOT_PERMITTED_SYMBOLS",
    "short_not_permitted_symbols",
    "short_allowed_symbols",
    "surveillance_blocked_symbols",
    "clear_eligibility_caches",
    "is_surveillance_blocked",
    "is_short_allowed",
    "is_corporate_action_blocked",
    "eligibility_flags",
]
