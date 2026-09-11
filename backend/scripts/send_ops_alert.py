"""Send a simple ops alert email via configured SES/SMTP (EMAIL_PROVIDER).

Usage (api container):

    python scripts/send_ops_alert.py --title "Subject" --body "plain text"
    python scripts/send_ops_alert.py --title "Subject" --body-json '{"status":"red",...}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.alerts.composer import ScanAlert
from app.application.alerts.email_delivery import deliver_email_alert
from app.core.config import get_settings


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def _format_body(title: str, body: str | None, body_json: str | None) -> str:
    lines = [title, "", "Mint token → update .env → ops/vps/restart_api_token.sh if live_ready is false.", ""]
    if body_json:
        try:
            payload = json.loads(body_json)
        except json.JSONDecodeError:
            lines.append(body_json)
            return "\n".join(lines)
        status = payload.get("status")
        ready = payload.get("ready")
        lines.append(f"status={status} ready={ready}")
        lines.append(f"provider_1d_max={payload.get('provider_1d_max')}")
        lines.append(f"calendar_1d_expected={payload.get('calendar_1d_expected')}")
        lines.append("")
        for gate in payload.get("gates") or []:
            if not isinstance(gate, dict):
                continue
            lines.append(
                f"- [{gate.get('status')}] {gate.get('id')}: {gate.get('detail')}"
            )
        recs = payload.get("recommendations") or []
        if recs:
            lines.append("")
            lines.append("Recommendations:")
            for rec in recs:
                lines.append(f"- {rec}")
        lines.append("")
        lines.append("Raw JSON truncated in logs; see /var/log/tradepilot/nifty500-readiness.log")
    elif body:
        lines.append(body)
    else:
        lines.append("(no body)")
    return "\n".join(lines)


async def _send(title: str, body: str) -> None:
    settings = get_settings()
    alert = ScanAlert(title=title, body=body)
    result = await deliver_email_alert(alert, settings=settings, subject_override=title)
    print(f"email_sent={result.email_sent} detail={result.detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send ops alert email via SES/SMTP")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default=None)
    parser.add_argument("--body-json", default=None, help="Readiness JSON payload string")
    parser.add_argument("--body-file", default=None, help="Path to readiness JSON file")
    args = parser.parse_args()
    body_json = args.body_json
    if args.body_file:
        body_json = Path(args.body_file).read_text(encoding="utf-8")
    text = _format_body(args.title, args.body, body_json)
    _run_async(_send(args.title, text))


if __name__ == "__main__":
    main()
