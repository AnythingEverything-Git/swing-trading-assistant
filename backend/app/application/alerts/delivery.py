"""Alert delivery. Always logs. Telegram is plug-in when tokens exist."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from app.application.alerts.composer import ScanAlert
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.alerts")


@dataclass(frozen=True)
class DeliveryResult:
    logged: bool
    telegram_sent: bool
    detail: str


async def deliver_alert(alert: ScanAlert, settings: Settings | None = None) -> DeliveryResult:
    settings = settings or get_settings()
    logger.info("scan.alert title=%s\n%s", alert.title, alert.body)

    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    if not token or not chat_id:
        return DeliveryResult(
            logged=True,
            telegram_sent=False,
            detail="Telegram not configured; alert logged only",
        )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"{alert.title}\n\n{alert.body}"},
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — delivery must not fail the scan
        logger.warning("telegram.delivery_failed: %s", exc)
        return DeliveryResult(logged=True, telegram_sent=False, detail=str(exc))

    return DeliveryResult(logged=True, telegram_sent=True, detail="sent")


__all__ = ["DeliveryResult", "deliver_alert"]
