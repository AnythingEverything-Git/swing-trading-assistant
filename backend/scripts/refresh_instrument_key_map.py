"""Refresh NSE trading-symbol -> Upstox instrument_key mappings from the public master.

Usage (from backend/):

    python scripts/refresh_instrument_key_map.py
"""
from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.infrastructure.universe import get_universe

_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_OUTPUT_PATH = (
    _BACKEND_ROOT
    / "app"
    / "infrastructure"
    / "market_data"
    / "data"
    / "nse_upstox_instrument_keys.json"
)


def main() -> None:
    wanted = set(get_universe("NIFTY_500").get_snapshot().symbols)
    print(f"downloading { _MASTER_URL}")
    with urllib.request.urlopen(_MASTER_URL, timeout=120) as response:
        records = json.loads(gzip.decompress(response.read()))

    mappings: dict[str, str] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        if item.get("instrument_type") != "EQ":
            continue
        if item.get("segment") != "NSE_EQ":
            continue
        symbol = str(item.get("trading_symbol") or "").strip().upper()
        key = str(item.get("instrument_key") or "").strip()
        if symbol in wanted and key:
            mappings[symbol] = key

    missing = sorted(wanted - set(mappings))
    payload = {
        "version": f"{date.today().isoformat()}-nse-eq-master",
        "source_note": (
            "Generated from Upstox public NSE instrument master (NSE_EQ / EQ) "
            "for packaged Nifty 500 symbols. Refresh when membership or ISINs change."
        ),
        "mappings": dict(sorted(mappings.items())),
    }
    _OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {_OUTPUT_PATH}")
    print(f"mapped={len(mappings)} missing={len(missing)}")
    if missing:
        print("missing_symbols=" + ",".join(missing))


if __name__ == "__main__":
    main()
