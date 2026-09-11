"""Unit tests for staged 1m history symbol resolution."""
from __future__ import annotations

from app.application.ops.history_backfill import resolve_stage_symbols
from app.infrastructure.universe import get_universe


def test_nifty_remaining_stages_are_nested_diffs():
    n50 = set(get_universe("NIFTY_50").get_snapshot().symbols)
    n100 = set(get_universe("NIFTY_100").get_snapshot().symbols)
    n500 = set(get_universe("NIFTY_500").get_snapshot().symbols)

    s50 = resolve_stage_symbols("NIFTY_50")
    s100r = resolve_stage_symbols("NIFTY_100_REMAINING")
    s500r = resolve_stage_symbols("NIFTY_500_REMAINING")

    assert set(s50) == n50
    assert set(s100r) == (n100 - n50)
    assert set(s500r) == (n500 - n100)
    assert not (set(s100r) & n50)
    assert not (set(s500r) & n100)
    assert len(s50) + len(s100r) == len(n100)
    assert len(n100) + len(s500r) == len(n500)
