"""Focused unit tests for the Nifty 500 universe abstraction."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.domain.universe import StockUniverse, UniverseSnapshot, normalize_symbol
from app.infrastructure.universe import Nifty500Universe, StaticFileStockUniverse


def test_nifty500_universe_returns_non_empty_symbols():
    universe: StockUniverse = Nifty500Universe()
    snapshot = universe.get_snapshot()

    assert isinstance(snapshot, UniverseSnapshot)
    assert snapshot.name == "NIFTY_500"
    assert snapshot.version
    assert len(snapshot.symbols) > 0


def test_nifty500_symbols_are_normalized_uppercase():
    snapshot = Nifty500Universe().get_snapshot()

    assert all(isinstance(symbol, str) for symbol in snapshot.symbols)
    assert all(symbol == symbol.strip().upper() for symbol in snapshot.symbols)
    assert all(symbol == normalize_symbol(symbol) for symbol in snapshot.symbols)


def test_nifty500_symbols_have_no_duplicates():
    symbols = Nifty500Universe().get_snapshot().symbols

    assert len(symbols) == len(set(symbols))


def test_nifty500_universe_is_deterministic():
    first = Nifty500Universe().get_snapshot()
    second = Nifty500Universe().get_snapshot()

    assert first == second
    assert first.symbols == second.symbols
    assert first.version == second.version
    assert first.as_of == second.as_of


def test_consumer_uses_abstraction_without_knowing_storage(tmp_path: Path):
    payload = {
        "name": "NIFTY_500",
        "version": "test-v1",
        "as_of": "2026-01-15",
        "symbols": [" reliance ", "TCS", "tcs", "INFY"],
    }
    path = tmp_path / "custom_universe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    universe: StockUniverse = StaticFileStockUniverse(path)
    snapshot = universe.get_snapshot()

    assert snapshot.name == "NIFTY_500"
    assert snapshot.version == "test-v1"
    assert snapshot.as_of == date(2026, 1, 15)
    assert snapshot.symbols == ("RELIANCE", "TCS", "INFY")
