"""First-5-minute RVOL for ORB V1."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from app.domain.intraday.config_v1 import IntradayConfigV1, DEFAULT_CONFIG_V1


def compute_rvol5(
    today_or_volume: int,
    prior_first_5m_volumes: Sequence[int],
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
) -> Decimal | None:
    """Return RVOL5 or None when history is insufficient."""
    need = config.rvol_lookback_sessions
    if len(prior_first_5m_volumes) < need:
        return None
    window = [int(v) for v in prior_first_5m_volumes[-need:]]
    if any(v <= 0 for v in window):
        return None
    mean = Decimal(sum(window)) / Decimal(need)
    if mean <= 0:
        return None
    return Decimal(today_or_volume) / mean


def prior_volumes_from_map(
    history: Mapping[date, int],
    session_date: date,
    lookback: int,
) -> list[int]:
    """Collect up to `lookback` volumes from sessions strictly before session_date."""
    prior_dates = sorted(d for d in history if d < session_date)
    if len(prior_dates) < lookback:
        return [history[d] for d in prior_dates]
    return [history[d] for d in prior_dates[-lookback:]]


__all__ = ["compute_rvol5", "prior_volumes_from_map"]
