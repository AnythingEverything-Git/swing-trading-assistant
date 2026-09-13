"""Run ORB certification package: backtest artifact + eligibility inventory + memo notes.

Does NOT flip the strategy to certified. Multi-year Upstox 1m must be present for a go.

Examples (from backend/):

    python scripts/run_intraday_certification.py --source demo --start 2026-09-01 --end 2026-09-07
    python scripts/run_intraday_certification.py --source persisted --start 2024-01-01 --end 2025-12-31 --holdout-frac 0.3
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.domain.intraday.asset_class import etf_universe_symbols, morning_universe_symbols
from app.domain.intraday.eligibility import (
    short_allowed_symbols,
    short_not_permitted_symbols,
    surveillance_blocked_symbols,
    _corporate_actions_payload,
)
from app.infrastructure.universe import get_universe


def _eligibility_inventory() -> dict:
    ordered, classes = morning_universe_symbols()
    stocks = sum(1 for s in ordered if classes[s] == "STOCK")
    etfs = sum(1 for s in ordered if classes[s] == "ETF")
    allow = short_allowed_symbols()
    return {
        "morning_universe_total": len(ordered),
        "morning_stocks": stocks,
        "morning_etfs": etfs,
        "nse_cash_count": len(get_universe("NSE_CASH").get_snapshot().symbols),
        "nse_etf_file_count": len(etf_universe_symbols()),
        "short_denylist_count": len(short_not_permitted_symbols()),
        "short_allowlist_count": None if allow is None else len(allow),
        "surveillance_blocked_today": len(surveillance_blocked_symbols(date.today())),
        "corporate_action_entries": len(_corporate_actions_payload()),
        "filters_file_backed": True,
        "note": (
            "Eligibility is file-backed PIT. Replace JSON dumps with exchange/broker exports "
            "before claiming live validation. Multi-year 1m OOS still required for go."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ORB V1 certification package runner")
    parser.add_argument("--source", choices=["demo", "persisted"], default="demo")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--holdout-frac", type=float, default=0.3)
    parser.add_argument("--cost-mult", default="2")
    parser.add_argument(
        "--universe",
        default="NIFTY_50",
        help="Universe for persisted/demo backtest (default NIFTY_50)",
    )
    parser.add_argument(
        "--out",
        default=str(_REPO_ROOT / "docs" / "artifacts" / "intraday_cert_package.json"),
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    backtest_out = out_path.with_name(out_path.stem + "_backtest.json")

    cmd = [
        sys.executable,
        str(_BACKEND_ROOT / "scripts" / "run_intraday_backtest.py"),
        "--source",
        args.source,
        "--start",
        args.start,
        "--end",
        args.end,
        "--holdout-frac",
        str(args.holdout_frac),
        "--cost-mult",
        str(args.cost_mult),
        "--universe",
        args.universe,
        "--out",
        str(backtest_out),
    ]
    print("running", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(_BACKEND_ROOT))
    backtest = json.loads(backtest_out.read_text(encoding="utf-8"))

    inventory = _eligibility_inventory()
    notes = list(backtest.get("go_no_go_notes") or [])
    decision = "NO_GO"
    if args.source == "persisted" and not notes:
        decision = "CONDITIONAL — review multi-year coverage + paper divergence before go"
    if any("Thin sample" in n or "concentrated" in n.lower() or "collapses" in n.lower() for n in notes):
        decision = "NO_GO"
    if args.source == "demo":
        notes.append("Demo source — automatic NO_GO for certification.")
        decision = "NO_GO"

    package = {
        "strategy_id": "NSE_STOCKS_ETF_ORB_RVOL_5M_V1",
        "config_hash": "CONFIG_V1",
        "generated_for": {"start": args.start, "end": args.end, "source": args.source},
        "decision": decision,
        "eligibility_inventory": inventory,
        "backtest_path": str(backtest_out.as_posix()),
        "backtest_summary": {
            "overall": backtest.get("overall"),
            "in_sample": backtest.get("in_sample"),
            "oos": backtest.get("oos"),
            "go_no_go_notes": notes,
        },
        "operator_checklist": [
            "Refresh universe: python scripts/build_nse_universe_from_upstox.py",
            "Multi-year 1m: python scripts/refresh_intraday_candles.py --mode range --universe NIFTY_50 --start YYYY-MM-DD --end YYYY-MM-DD",
            "Update surveillance_blocked.json / corporate_actions.json / short_allowed.json from official dumps",
            "Collect practice divergence over live mornings",
            "Paste decision into docs/INTRADAY_CERTIFICATION_V1.md — never retune CONFIG_V1",
        ],
    }
    out_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"decision={decision}")


if __name__ == "__main__":
    main()
