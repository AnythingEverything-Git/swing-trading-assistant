"""Send Morning / EOD brief emails from a stored scan run via SES/SMTP."""
from __future__ import annotations

from html import escape
from typing import Any, Literal
from urllib.parse import urlencode

from app.application.alerts.composer import ScanAlert
from app.application.alerts.email_delivery import (
    EmailDeliveryResult,
    deliver_email_alert,
    resolve_smtp_target,
)
from app.core.config import Settings, get_settings

BriefMode = Literal["morning", "eod"]


def _format_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _open_scan_link(frontend_base_url: str | None, scan_run_id: int | None) -> str | None:
    base = (frontend_base_url or "").rstrip("/")
    if not base or scan_run_id is None:
        return None
    return f"{base}/?{urlencode({'view': 'scan', 'run': str(scan_run_id)})}"


def _top_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = payload.get("top") or payload.get("opportunities") or []
    if not isinstance(ranked, list):
        return []
    return [item for item in ranked[:5] if isinstance(item, dict)]


def compose_brief_alert_from_payload(
    payload: dict[str, Any],
    *,
    mode: BriefMode,
    scan_run_id: int | None = None,
    frontend_base_url: str | None = None,
) -> ScanAlert:
    """Build a brief email from a stored OpportunityScanResponse payload."""
    label = "EOD" if mode == "eod" else "Morning"
    universe = str(payload.get("universe_name") or "NSE")
    eligible = int(payload.get("eligible_count") or 0)
    forming = int(payload.get("forming_count") or 0)
    scanned = int(payload.get("symbols_scanned") or 0)
    data_claim = str(payload.get("data_claim") or "Scan snapshot")
    ai_brief = (payload.get("ai_brief") or "").strip() or None
    alert_preview = (payload.get("alert_preview") or "").strip() or None
    dq = payload.get("data_quality_bullets") or []
    if not isinstance(dq, list):
        dq = []
    dq_lines = [str(b) for b in dq[:6] if b]

    open_link = _open_scan_link(frontend_base_url, scan_run_id)
    title = f"TradePilot {label} brief — {eligible} eligible"

    top = _top_items(payload)
    top_lines: list[str] = []
    top_rows_html: list[str] = []
    for index, item in enumerate(top, start=1):
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        symbol = str(item.get("symbol") or "—")
        entry = _format_money(candidate.get("entry_price"))
        stop = _format_money(candidate.get("stop_loss"))
        target = _format_money(candidate.get("target"))
        direction = str(candidate.get("direction") or "")
        top_lines.append(f"{index}. {symbol} {direction} · Entry {entry} · Stop {stop} · Tgt {target}")
        top_rows_html.append(
            "<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;'>{index}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;'><strong>{escape(symbol)}</strong></td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;'>{escape(direction)}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(entry)}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(stop)}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;'>{escape(target)}</td>"
            "</tr>"
        )
    if not top_lines:
        top_lines.append("No eligible names in this scan.")
        top_rows_html.append(
            "<tr><td colspan='6' style='padding:12px;color:#6b7280;'>No eligible names in this scan.</td></tr>"
        )

    body_parts = [
        f"TradePilot {label} brief",
        "=" * 42,
        "",
        data_claim,
        f"Universe: {universe}",
        f"Eligible: {eligible}  |  Forming: {forming}  |  Scanned: {scanned}",
        "",
    ]
    if ai_brief:
        body_parts.extend(["AI brief", "-" * 42, ai_brief, ""])
    elif alert_preview:
        body_parts.extend(["Scan alert", "-" * 42, alert_preview, ""])
    body_parts.extend(["Top ideas", "-" * 42, *top_lines, ""])
    if dq_lines:
        body_parts.extend(["Data quality notes", "-" * 42, *[f"- {b}" for b in dq_lines], ""])
    if open_link:
        body_parts.append(f"Open this scan: {open_link}")
    body_parts.extend(
        [
            "",
            "Warning: No promissory returns.",
            "Educational decision support only — not investment advice.",
            "TradePilot does not place orders.",
        ]
    )
    body = "\n".join(body_parts)

    brief_html = ""
    if ai_brief:
        brief_html = (
            "<div style='font-size:15px;font-weight:600;margin:8px 0 6px;'>AI brief</div>"
            f"<div style='font-size:13px;line-height:1.5;margin-bottom:14px;white-space:pre-wrap;'>"
            f"{escape(ai_brief)}</div>"
        )
    dq_html = "".join(
        f"<div style='font-size:12px;color:#6b7280;margin:2px 0;'>• {escape(b)}</div>" for b in dq_lines[:4]
    )
    open_html = ""
    if open_link:
        open_html = (
            f"<div style='margin:14px 0 4px;'>"
            f"<a href='{escape(open_link)}' style='display:inline-block;padding:10px 16px;"
            f"background:#0f766e;color:#ffffff;border-radius:8px;text-decoration:none;font-weight:600;'>"
            f"Open this scan</a></div>"
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
            <div style="font-size:22px;font-weight:700;margin-top:4px;">{escape(label)} brief</div>
            <div style="font-size:13px;margin-top:8px;opacity:0.85;">{escape(data_claim)}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 24px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:16px;">
              <tr>
                <td style="padding:10px 12px;background:#f8fafc;border-radius:8px;">
                  <div style="font-size:12px;color:#6b7280;">Universe</div>
                  <div style="font-size:16px;font-weight:600;">{escape(universe.replace('_', ' '))}</div>
                </td>
                <td width="8"></td>
                <td style="padding:10px 12px;background:#ecfdf5;border-radius:8px;">
                  <div style="font-size:12px;color:#047857;">Eligible</div>
                  <div style="font-size:16px;font-weight:600;">{eligible}</div>
                </td>
                <td width="8"></td>
                <td style="padding:10px 12px;background:#eff6ff;border-radius:8px;">
                  <div style="font-size:12px;color:#1d4ed8;">Forming</div>
                  <div style="font-size:16px;font-weight:600;">{forming}</div>
                </td>
                <td width="8"></td>
                <td style="padding:10px 12px;background:#f8fafc;border-radius:8px;">
                  <div style="font-size:12px;color:#6b7280;">Scanned</div>
                  <div style="font-size:16px;font-weight:600;">{scanned}</div>
                </td>
              </tr>
            </table>
            {brief_html}
            {dq_html}
            <div style="font-size:15px;font-weight:600;margin:8px 0 10px;">Top ideas</div>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;font-size:13px;">
              <thead>
                <tr style="background:#f9fafb;color:#6b7280;text-align:left;">
                  <th style="padding:8px;">#</th>
                  <th style="padding:8px;">Symbol</th>
                  <th style="padding:8px;">Side</th>
                  <th style="padding:8px;text-align:right;">Entry</th>
                  <th style="padding:8px;text-align:right;">Stop</th>
                  <th style="padding:8px;text-align:right;">Target</th>
                </tr>
              </thead>
              <tbody>
                {''.join(top_rows_html)}
              </tbody>
            </table>
            {open_html}
            <p style="font-size:12px;color:#b45309;margin:14px 0 0;">Warning: No promissory returns.</p>
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


async def send_brief_email(
    payload: dict[str, Any],
    *,
    mode: BriefMode,
    scan_run_id: int | None = None,
    settings: Settings | None = None,
) -> tuple[ScanAlert, EmailDeliveryResult]:
    settings = settings or get_settings()
    target = resolve_smtp_target(settings)
    if isinstance(target, str):
        alert = compose_brief_alert_from_payload(
            payload,
            mode=mode,
            scan_run_id=scan_run_id,
            frontend_base_url=settings.frontend_base_url,
        )
        return alert, EmailDeliveryResult(logged=True, email_sent=False, detail=target)

    alert = compose_brief_alert_from_payload(
        payload,
        mode=mode,
        scan_run_id=scan_run_id,
        frontend_base_url=settings.frontend_base_url,
    )
    result = await deliver_email_alert(alert, settings=settings)
    return alert, result


__all__ = [
    "BriefMode",
    "compose_brief_alert_from_payload",
    "send_brief_email",
]
