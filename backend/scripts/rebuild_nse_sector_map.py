"""Rebuild nse_sector_map industries from Nifty Total Market list.

Usage:
  python backend/scripts/rebuild_nse_sector_map.py
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from collections import Counter
from pathlib import Path

URL = "https://raw.githubusercontent.com/as1605/trading/main/indices/ind_niftytotalmarket_list.csv"
PATH = Path(__file__).resolve().parents[1] / "app" / "infrastructure" / "universe" / "data" / "nse_sector_map.json"


def coarse(industry: str) -> str:
    u = (industry or "").upper()
    if any(k in u for k in ("BANK", "FINANC", "NBFC", "INSURANCE", "CAPITAL MARKETS")):
        return "BANKING"
    if any(k in u for k in ("INFORMATION TECHNOLOGY", "SOFTWARE", "TECHNOLOGY")):
        return "IT"
    if any(k in u for k in ("OIL", "GAS", "PETRO", "ENERGY", "POWER", "CONSUMABLE FUEL")):
        return "ENERGY"
    if any(k in u for k in ("AUTO", "AUTOMOBILE")):
        return "AUTO"
    if any(k in u for k in ("PHARMA", "HEALTHCARE", "HEALTH CARE", "BIOTECH")):
        return "PHARMA"
    if any(k in u for k in ("FMCG", "CONSUMER", "FOOD", "BEVERAGE", "PERSONAL")):
        return "FMCG"
    if any(k in u for k in ("METAL", "MINING", "STEEL", "ALUMINIUM", "COPPER")):
        return "METALS"
    return "UNKNOWN"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": "TradePilot/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    sectors: dict[str, str] = {}
    industries: dict[str, str] = {}
    for row in rows:
        sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
        ind = (row.get("Industry") or row.get("industry") or "").strip()
        if not sym or not ind:
            continue
        industries[sym] = ind
        sectors[sym] = coarse(ind)

    existing = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    old = existing.get("sectors") or {}
    merged_sectors = {str(k).upper(): "UNKNOWN" for k in old}
    merged_sectors.update(sectors)

    out = {
        "as_of": existing.get("as_of"),
        "generated_at": existing.get("generated_at"),
        "source": "nse_nifty_total_market_industry + upstox_universe",
        "source_note": (
            "Industry from Nifty Total Market list; coarse sector for filters. "
            "UNKNOWN when unmapped."
        ),
        "sectors": dict(sorted(merged_sectors.items())),
        "industries": dict(sorted(industries.items())),
    }
    PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", PATH)
    print("industries", len(industries), Counter(sectors.values()))
    print("RELIANCE", out["sectors"].get("RELIANCE"), out["industries"].get("RELIANCE"))


if __name__ == "__main__":
    main()
