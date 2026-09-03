"""Compose trader-facing alert copy from a presented scan. Delivery is optional."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.application.scan.scan_presentation import PresentedScan


@dataclass(frozen=True)
class ScanAlert:
    title: str
    body: str
    html_body: str | None = None


def _format_money(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def compose_scan_alert(presented: PresentedScan, *, universe_name: str, data_claim: str) -> ScanAlert:
    top_lines: list[str] = []
    top_rows_html: list[str] = []
    for item in presented.top:
        candidate = item.opportunity.candidate
        qty = item.quantity if item.quantity is not None else "—"
        line = (
            f"{item.rank}. {item.opportunity.symbol}  "
            f"Entry {_format_money(candidate.entry_price)}  "
            f"SL {_format_money(candidate.stop_loss)}  "
            f"Tgt {_format_money(candidate.target)}  "
            f"R:R {_format_money(candidate.risk_reward_ratio)}  "
            f"score {_format_money(item.quality.score)}  "
            f"qty {qty}"
        )
        top_lines.append(line)
        top_rows_html.append(
            "<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;'>{item.rank}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;'><strong>{escape(item.opportunity.symbol)}</strong></td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(_format_money(candidate.entry_price))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(_format_money(candidate.stop_loss))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(_format_money(candidate.target))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(_format_money(candidate.risk_reward_ratio))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(_format_money(item.quality.score))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(str(qty))}</td>"
            "</tr>"
        )

    if not top_lines:
        top_lines.append("No eligible names in this scan.")
        top_rows_html.append(
            "<tr><td colspan='8' style='padding:12px;color:#6b7280;'>No eligible names in this scan.</td></tr>"
        )

    forming_preview = ", ".join(item.forming.symbol for item in presented.forming[:8]) or "none"
    title = f"TradePilot {universe_name} — {presented.report.eligible_count} eligible"
    body = (
        f"TradePilot AI — Swing Opportunity Alert\n"
        f"{'=' * 42}\n\n"
        f"{data_claim}\n"
        f"Universe: {universe_name}\n"
        f"Eligible: {presented.report.eligible_count}  |  "
        f"Forming: {presented.report.forming_count}  |  "
        f"Scanned: {presented.report.symbols_scanned}\n\n"
        f"Top setups\n"
        f"{'-' * 42}\n"
        + "\n".join(top_lines)
        + "\n\n"
        f"Forming watchlist: {forming_preview}\n\n"
        f"Educational decision support only — not investment advice.\n"
        f"TradePilot does not place orders."
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Segoe UI,Arial,sans-serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
        <tr>
          <td style="background:#0f172a;color:#ffffff;padding:20px 24px;">
            <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.8;">TradePilot AI</div>
            <div style="font-size:22px;font-weight:700;margin-top:4px;">Swing Opportunity Alert</div>
            <div style="font-size:13px;margin-top:8px;opacity:0.85;">{escape(data_claim)}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 24px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:16px;">
              <tr>
                <td style="padding:10px 12px;background:#f8fafc;border-radius:8px;">
                  <div style="font-size:12px;color:#6b7280;">Universe</div>
                  <div style="font-size:16px;font-weight:600;">{escape(universe_name.replace('_', ' '))}</div>
                </td>
                <td width="8"></td>
                <td style="padding:10px 12px;background:#ecfdf5;border-radius:8px;">
                  <div style="font-size:12px;color:#047857;">Eligible</div>
                  <div style="font-size:16px;font-weight:600;">{presented.report.eligible_count}</div>
                </td>
                <td width="8"></td>
                <td style="padding:10px 12px;background:#eff6ff;border-radius:8px;">
                  <div style="font-size:12px;color:#1d4ed8;">Forming</div>
                  <div style="font-size:16px;font-weight:600;">{presented.report.forming_count}</div>
                </td>
                <td width="8"></td>
                <td style="padding:10px 12px;background:#f8fafc;border-radius:8px;">
                  <div style="font-size:12px;color:#6b7280;">Scanned</div>
                  <div style="font-size:16px;font-weight:600;">{presented.report.symbols_scanned}</div>
                </td>
              </tr>
            </table>

            <div style="font-size:15px;font-weight:600;margin:8px 0 10px;">Top setups</div>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;font-size:13px;">
              <thead>
                <tr style="background:#f9fafb;color:#6b7280;text-align:left;">
                  <th style="padding:8px;">#</th>
                  <th style="padding:8px;">Symbol</th>
                  <th style="padding:8px;text-align:right;">Entry</th>
                  <th style="padding:8px;text-align:right;">SL</th>
                  <th style="padding:8px;text-align:right;">Target</th>
                  <th style="padding:8px;text-align:right;">R:R</th>
                  <th style="padding:8px;text-align:right;">Score</th>
                  <th style="padding:8px;text-align:right;">Qty</th>
                </tr>
              </thead>
              <tbody>
                {''.join(top_rows_html)}
              </tbody>
            </table>

            <div style="margin-top:16px;font-size:13px;color:#374151;">
              <strong>Forming watchlist:</strong> {escape(forming_preview)}
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:14px 24px;background:#f9fafb;color:#6b7280;font-size:12px;border-top:1px solid #e5e7eb;">
            Educational decision support only — not investment advice. TradePilot does not place orders.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return ScanAlert(title=title, body=body, html_body=html_body)


def compose_confirmation_alert(*, symbols: list[str], lines: list[str]) -> ScanAlert:
    count = len(symbols)
    title = f"TradePilot Confirmation Alert — {count} new"
    body = (
        f"TradePilot AI — New Confirmation(s)\n"
        f"{'=' * 42}\n\n"
        f"{count} stock(s) moved to confirmed setup:\n\n"
        + "\n".join(lines)
        + "\n\nEducational decision support only — not investment advice."
    )
    rows = "".join(
        f"<li style='margin:6px 0;'>{escape(line)}</li>" for line in lines
    )
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Segoe UI,Arial,sans-serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
        <tr>
          <td style="background:#065f46;color:#ffffff;padding:20px 24px;">
            <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.8;">TradePilot AI</div>
            <div style="font-size:22px;font-weight:700;margin-top:4px;">New Confirmation Alert</div>
            <div style="font-size:13px;margin-top:8px;opacity:0.9;">{count} newly confirmed setup(s)</div>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 24px;">
            <ul style="padding-left:18px;margin:0;font-size:14px;line-height:1.5;">{rows}</ul>
          </td>
        </tr>
        <tr>
          <td style="padding:14px 24px;background:#f9fafb;color:#6b7280;font-size:12px;border-top:1px solid #e5e7eb;">
            Educational decision support only — not investment advice. TradePilot does not place orders.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return ScanAlert(title=title, body=body, html_body=html_body)


__all__ = ["ScanAlert", "compose_scan_alert", "compose_confirmation_alert"]
