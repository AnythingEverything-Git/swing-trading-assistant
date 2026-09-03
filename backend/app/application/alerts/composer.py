"""Compose trader-facing alert copy from a presented scan. Delivery is optional."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.scan.scan_presentation import PresentedScan


@dataclass(frozen=True)
class ScanAlert:
    title: str
    body: str


def compose_scan_alert(presented: PresentedScan, *, universe_name: str, data_claim: str) -> ScanAlert:
    top_lines = []
    for item in presented.top:
        candidate = item.opportunity.candidate
        top_lines.append(
            f"{item.rank}. {item.opportunity.symbol}  "
            f"Entry {candidate.entry_price}  SL {candidate.stop_loss}  "
            f"Tgt {candidate.target}  score {item.quality.score}"
        )
    if not top_lines:
        top_lines.append("No eligible names in this scan.")

    forming_preview = ", ".join(item.forming.symbol for item in presented.forming[:8]) or "none"
    body = (
        f"{data_claim}\n"
        f"{universe_name}: {presented.report.eligible_count} eligible, "
        f"{presented.report.forming_count} forming, "
        f"{presented.report.symbols_scanned} scanned.\n\n"
        f"Top setups:\n" + "\n".join(top_lines) + "\n\n"
        f"Forming watchlist: {forming_preview}\n"
        f"Educational decision support — not investment advice."
    )
    return ScanAlert(title=f"TradePilot {universe_name} Top {len(presented.top)}", body=body)


__all__ = ["ScanAlert", "compose_scan_alert"]
