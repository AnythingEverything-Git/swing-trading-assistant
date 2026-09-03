"""File-backed stock universe implementations.

Constituent membership is loaded from versioned static data files so the
scanner is not coupled to an external website or live index API.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from app.domain.universe.universe import StockUniverse, UniverseSnapshot, normalize_symbols

_DATA_DIR = Path(__file__).resolve().parent / "data"

UniverseName = Literal["NIFTY_50", "NIFTY_100", "NIFTY_200", "NIFTY_500"]

_UNIVERSE_FILES: dict[UniverseName, Path] = {
    "NIFTY_50": _DATA_DIR / "nifty_50_constituents.json",
    "NIFTY_100": _DATA_DIR / "nifty_100_constituents.json",
    "NIFTY_200": _DATA_DIR / "nifty_200_constituents.json",
    "NIFTY_500": _DATA_DIR / "nifty500_constituents.json",
}

SUPPORTED_UNIVERSE_NAMES: tuple[UniverseName, ...] = (
    "NIFTY_50",
    "NIFTY_100",
    "NIFTY_200",
    "NIFTY_500",
)


class StaticFileStockUniverse:
    """Deterministic StockUniverse backed by a JSON constituents file.

    Expected JSON shape:
      {
        "name": "NIFTY_500",
        "version": "...",
        "as_of": "YYYY-MM-DD" | null,
        "symbols": ["RELIANCE", ...]
      }
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def get_snapshot(self) -> UniverseSnapshot:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"universe file must contain a JSON object: {self._path}")

        name = raw.get("name")
        version = raw.get("version")
        symbols_raw = raw.get("symbols")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("universe file requires a non-empty string 'name'")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("universe file requires a non-empty string 'version'")
        if not isinstance(symbols_raw, list):
            raise ValueError("universe file requires a list 'symbols'")

        as_of = _parse_as_of(raw.get("as_of"))
        symbols = normalize_symbols(str(item) for item in symbols_raw)
        return UniverseSnapshot(name=name.strip(), version=version.strip(), as_of=as_of, symbols=symbols)


class Nifty500Universe(StaticFileStockUniverse):
    """Nifty 500 constituents from the packaged replaceable snapshot file."""

    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__(path or _UNIVERSE_FILES["NIFTY_500"])


class Nifty200Universe(StaticFileStockUniverse):
    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__(path or _UNIVERSE_FILES["NIFTY_200"])


class Nifty100Universe(StaticFileStockUniverse):
    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__(path or _UNIVERSE_FILES["NIFTY_100"])


class Nifty50Universe(StaticFileStockUniverse):
    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__(path or _UNIVERSE_FILES["NIFTY_50"])


def get_universe(name: str) -> StockUniverse:
    """Resolve a supported index universe by name."""
    key = name.strip().upper()
    if key not in _UNIVERSE_FILES:
        supported = ", ".join(SUPPORTED_UNIVERSE_NAMES)
        raise ValueError(f"unsupported universe '{name}'; expected one of: {supported}")
    return StaticFileStockUniverse(_UNIVERSE_FILES[key])  # type: ignore[index]


def _parse_as_of(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("as_of must be an ISO date string, date, or null")


__all__ = [
    "StaticFileStockUniverse",
    "Nifty500Universe",
    "Nifty200Universe",
    "Nifty100Universe",
    "Nifty50Universe",
    "UniverseName",
    "SUPPORTED_UNIVERSE_NAMES",
    "get_universe",
]
