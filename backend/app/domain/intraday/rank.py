"""Deterministic ranking for ORB V1 — stocks and ETFs ranked separately."""
from __future__ import annotations

from typing import Sequence

from app.domain.intraday.config_v1 import IntradayConfigV1, DEFAULT_CONFIG_V1
from app.domain.intraday.types import RankedCandidate, ScreenCandidate


def _sort_key(c: ScreenCandidate):
    return (
        -c.rvol5,
        -c.opening_range.expansion_pct,
        -c.adv_value,
        c.instrument_id,
    )


def rank_candidates(
    candidates: Sequence[ScreenCandidate],
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
    *,
    top_n: int | None = None,
) -> list[RankedCandidate]:
    """Filter RVOL, sort, assign ranks, keep TOP_N."""
    limit = config.top_n if top_n is None else top_n
    eligible = [c for c in candidates if c.rvol5 >= config.min_rvol5]
    ordered = sorted(eligible, key=_sort_key)
    top = ordered[:limit]
    return [RankedCandidate(candidate=c, rank=i + 1) for i, c in enumerate(top)]


def rank_candidates_split(
    candidates: Sequence[ScreenCandidate],
    config: IntradayConfigV1 = DEFAULT_CONFIG_V1,
    *,
    top_n_stocks: int | None = None,
    top_n_etfs: int | None = None,
) -> tuple[list[RankedCandidate], list[RankedCandidate]]:
    """Rank STOCK and ETF pools independently (same RVOL rules, separate Top-N)."""
    stocks = [c for c in candidates if getattr(c, "asset_class", "STOCK") != "ETF"]
    etfs = [c for c in candidates if getattr(c, "asset_class", "STOCK") == "ETF"]
    stock_n = config.top_n if top_n_stocks is None else top_n_stocks
    etf_n = config.top_n if top_n_etfs is None else top_n_etfs
    return (
        rank_candidates(stocks, config, top_n=stock_n),
        rank_candidates(etfs, config, top_n=etf_n),
    )


__all__ = ["rank_candidates", "rank_candidates_split"]
