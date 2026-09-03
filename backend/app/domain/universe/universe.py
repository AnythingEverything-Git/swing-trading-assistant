"""Domain stock-universe abstractions.

A universe answers only which symbols belong to a named market set.
It does not evaluate trading eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence


@dataclass(frozen=True)
class UniverseSnapshot:
    """Versioned constituent snapshot for a named universe."""

    name: str
    version: str
    as_of: date | None
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not self.version or not self.version.strip():
            raise ValueError("version must be a non-empty string")
        if not isinstance(self.symbols, tuple):
            object.__setattr__(self, "symbols", tuple(self.symbols))


class StockUniverse(Protocol):
    """Replaceable source of constituent symbols for a market universe."""

    def get_snapshot(self) -> UniverseSnapshot:  # pragma: no cover - interface
        """Return the current versioned constituent snapshot."""


def normalize_symbol(symbol: str) -> str:
    """Normalize a ticker to the repository convention: stripped uppercase."""
    if not isinstance(symbol, str):
        raise TypeError("symbol must be a string")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must be a non-empty string")
    return normalized


def normalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Normalize symbols, drop empties via validation, and dedupe preserving order."""
    ordered: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


__all__ = [
    "UniverseSnapshot",
    "StockUniverse",
    "normalize_symbol",
    "normalize_symbols",
]
