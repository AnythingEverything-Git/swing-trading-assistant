"""Build NSE cash + ETF universe files and Upstox instrument keys from the public master.

Usage (from backend/):

    python scripts/build_nse_universe_from_upstox.py
    python scripts/build_nse_universe_from_upstox.py --keys-only
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_UNIVERSE_DIR = _BACKEND_ROOT / "app" / "infrastructure" / "universe" / "data"
_KEYS_PATH = (
    _BACKEND_ROOT / "app" / "infrastructure" / "market_data" / "data" / "nse_upstox_instrument_keys.json"
)

_ETF_TYPE_HINTS = {"ETF", "EQ", "ID", "IDX"}  # Upstox uses various; we also use name heuristics
_ETF_NAME_MARKERS = ("ETF", "BEES", "IETF", "GOLD", "SILVER", "NIFTY", "SENSEX", "BANKBEES")


def _is_etf(item: dict) -> bool:
    itype = str(item.get("instrument_type") or "").strip().upper()
    name = str(item.get("name") or "").upper()
    symbol = str(item.get("trading_symbol") or "").upper()
    if itype in {"ETF"}:
        return True
    if symbol.endswith("BEES") or symbol.endswith("ETF") or symbol.endswith("IETF"):
        return True
    if " ETF" in f" {name}" or name.endswith("ETF"):
        return True
    # Curated liquid cash ETFs often typed EQ on Upstox — keep suffix heuristics.
    if any(m in symbol for m in ("BEES", "IETF")):
        return True
    return False


def _is_cash_eq(item: dict) -> bool:
    if item.get("segment") != "NSE_EQ":
        return False
    itype = str(item.get("instrument_type") or "").strip().upper()
    return itype in {"EQ", "ETF"}


def _sector(item: dict) -> str:
    for key in ("sector", "industry", "asset_type"):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build NSE cash/ETF universe from Upstox master")
    parser.add_argument("--keys-only", action="store_true", help="Only refresh instrument keys for existing universes")
    parser.add_argument("--url", default=_MASTER_URL)
    args = parser.parse_args()

    print(f"downloading {args.url}")
    with urllib.request.urlopen(args.url, timeout=180) as response:
        records = json.loads(gzip.decompress(response.read()))

    cash: list[str] = []
    etfs: list[str] = []
    sectors: dict[str, str] = {}
    mappings: dict[str, str] = {}
    seen_cash: set[str] = set()
    seen_etf: set[str] = set()

    for item in records:
        if not isinstance(item, dict) or not _is_cash_eq(item):
            continue
        symbol = str(item.get("trading_symbol") or "").strip().upper()
        key = str(item.get("instrument_key") or "").strip()
        if not symbol or not key:
            continue
        # Skip series suffixes / odd lots that aren't plain cash tickers
        if " " in symbol or "-" in symbol:
            continue
        mappings[symbol] = key
        sectors[symbol] = _sector(item)
        if _is_etf(item):
            if symbol not in seen_etf:
                etfs.append(symbol)
                seen_etf.add(symbol)
        else:
            if symbol not in seen_cash:
                cash.append(symbol)
                seen_cash.add(symbol)

    cash.sort()
    etfs.sort()
    today = date.today().isoformat()

    if not args.keys_only:
        cash_path = _UNIVERSE_DIR / "nse_cash_eq_constituents.json"
        etf_path = _UNIVERSE_DIR / "nse_etf_constituents.json"
        sector_path = _UNIVERSE_DIR / "nse_sector_map.json"
        cash_path.write_text(
            json.dumps(
                {
                    "name": "NSE_CASH",
                    "version": f"{today}-upstox-nse-eq",
                    "as_of": today,
                    "source_note": (
                        "All NSE_EQ EQ symbols from Upstox public instrument master "
                        "(excludes ETFs classified separately). Refresh periodically."
                    ),
                    "symbols": cash,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        etf_path.write_text(
            json.dumps(
                {
                    "name": "NSE_ETF",
                    "version": f"{today}-upstox-nse-etf",
                    "as_of": today,
                    "source_note": (
                        "NSE cash ETFs inferred from Upstox master (instrument_type ETF "
                        "and/or BEES/ETF/IETF trading-symbol heuristics)."
                    ),
                    "symbols": etfs,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sector_path.write_text(
            json.dumps(
                {
                    "name": "NSE_SECTOR_MAP",
                    "version": f"{today}-upstox",
                    "as_of": today,
                    "source_note": "Best-effort sector/industry from Upstox master fields when present.",
                    "sectors": dict(sorted(sectors.items())),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {cash_path} symbols={len(cash)}")
        print(f"wrote {etf_path} symbols={len(etfs)}")
        print(f"wrote {sector_path} symbols={len(sectors)}")

    # Keep Nifty-scoped keys plus full morning universe for live fetch coverage.
    from app.infrastructure.universe import get_universe

    wanted = set(get_universe("NIFTY_500").get_snapshot().symbols)
    wanted.update(cash)
    wanted.update(etfs)
    scoped = {s: mappings[s] for s in sorted(wanted) if s in mappings}
    _KEYS_PATH.write_text(
        json.dumps(
            {
                "version": f"{today}-nse-cash-etf-master",
                "source_note": (
                    "Upstox instrument_key map for NSE cash EQ + ETF universe "
                    "(plus Nifty 500 overlap). Refresh with build_nse_universe_from_upstox.py."
                ),
                "mappings": scoped,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {_KEYS_PATH} mapped={len(scoped)}")


if __name__ == "__main__":
    main()
