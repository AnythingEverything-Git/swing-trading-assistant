"""Alert delivery. Always logs. Email + Telegram are plug-in when configured."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from app.application.alerts.composer import ScanAlert
from app.application.alerts.email_delivery import deliver_email_alert
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.alerts")


@dataclass(frozen=True)
class DeliveryResult:
    logged: bool
    telegram_sent: bool
    email_sent: bool
    detail: str


async def deliver_alert(
    alert: ScanAlert,
    settings: Settings | None = None,
    *,
    subject_override: str | None = None,
) -> DeliveryResult:
    settings = settings or get_settings()
    logger.info("scan.alert title=%s\n%s", alert.title, alert.body)

    # --- Email delivery ---
    email_result = await deliver_email_alert(alert, settings=settings, subject_override=subject_override)

    # --- Telegram delivery ---
    telegram_sent = False
    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    if token and chat_id:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"{alert.title}\n\n{alert.body}"},
                )
                response.raise_for_status()
            telegram_sent = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram.delivery_failed: %s", exc)

    details = []
    if email_result.email_sent:
        details.append("email sent")
    else:
        details.append(f"email: {email_result.detail}")
    details.append("telegram sent" if telegram_sent else "telegram not sent")

    return DeliveryResult(
        logged=True,
        telegram_sent=telegram_sent,
        email_sent=email_result.email_sent,
        detail="; ".join(details),
    )


__all__ = ["DeliveryResult", "deliver_alert"]
