"""Classify NSE symbols as STOCK vs ETF for ORB morning board."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

AssetClass = Literal["STOCK", "ETF"]

_DATA_DIR = Path(__file__).resolve().parents[2] / "infrastructure" / "universe" / "data"


@lru_cache(maxsize=1)
def etf_universe_symbols() -> frozenset[str]:
    path = _DATA_DIR / "nse_etf_constituents.json"
    if not path.exists():
        return frozenset()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        symbols = raw.get("symbols") if isinstance(raw, dict) else []
    except (OSError, json.JSONDecodeError, TypeError):
        return frozenset()
    return frozenset(str(s).strip().upper() for s in symbols if str(s).strip())


@lru_cache(maxsize=1)
def sector_map() -> dict[str, str]:
    path = _DATA_DIR / "nse_sector_map.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        sectors = raw.get("sectors") if isinstance(raw, dict) else {}
        if not isinstance(sectors, dict):
            return {}
        return {str(k).upper(): str(v) for k, v in sectors.items()}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def classify_asset_class(symbol: str) -> AssetClass:
    sym = symbol.strip().upper()
    if sym in etf_universe_symbols():
        return "ETF"
    if sym.endswith("BEES") or sym.endswith("ETF") or sym.endswith("IETF"):
        return "ETF"
    return "STOCK"


def morning_universe_symbols() -> tuple[tuple[str, ...], dict[str, AssetClass]]:
    """Full NSE_ALL (cash EQ + ETFs); ETF class wins on overlap."""
    from app.infrastructure.universe import get_universe

    snap = get_universe("NSE_ALL").get_snapshot()
    etfs = etf_universe_symbols()
    classes: dict[str, AssetClass] = {}
    ordered: list[str] = []
    for s in snap.symbols:
        classes[s] = "ETF" if s in etfs or classify_asset_class(s) == "ETF" else "STOCK"
        ordered.append(s)
    return tuple(ordered), classes


__all__ = [
    "AssetClass",
    "etf_universe_symbols",
    "sector_map",
    "classify_asset_class",
    "morning_universe_symbols",
]
