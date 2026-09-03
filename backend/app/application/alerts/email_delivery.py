"""Email alert delivery via Amazon SES SMTP (default) or generic SMTP."""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.application.alerts.composer import ScanAlert
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.alerts.email")


@dataclass(frozen=True)
class EmailDeliveryResult:
    logged: bool
    email_sent: bool
    detail: str


@dataclass(frozen=True)
class SmtpTarget:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_addr: str
    recipients: tuple[str, ...]
    provider: str


def _parse_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def ses_smtp_host(region: str) -> str:
    return f"email-smtp.{region.strip()}.amazonaws.com"


def _clean_secret(value: str | None) -> str:
    text = (value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def resolve_smtp_target(settings: Settings) -> SmtpTarget | str:
    """Return SMTP settings, or a string explaining why email cannot be sent."""
    from_addr = (settings.alert_from_email or "").strip()
    recipients = tuple(_parse_recipients(settings.alert_to_emails))
    if not from_addr or not recipients:
        return "Email not configured (ALERT_FROM_EMAIL or ALERT_TO_EMAILS missing); alert logged only"

    provider = (settings.email_provider or "ses").strip().lower()
    port = settings.smtp_port
    use_tls = settings.smtp_use_tls

    if provider == "ses":
        region = (settings.aws_ses_region or "ap-south-1").strip()
        host = (settings.smtp_host or ses_smtp_host(region)).strip()
        username = _clean_secret(settings.aws_ses_smtp_username or settings.smtp_user)
        password = _clean_secret(settings.aws_ses_smtp_password or settings.smtp_password)
        if not username or not password:
            return (
                "Amazon SES SMTP credentials missing "
                "(AWS_SES_SMTP_USERNAME / AWS_SES_SMTP_PASSWORD); alert logged only"
            )
        return SmtpTarget(
            host=host,
            port=port,
            username=username,
            password=password,
            use_tls=use_tls,
            from_addr=from_addr,
            recipients=recipients,
            provider="ses",
        )

    host = (settings.smtp_host or "").strip()
    username = _clean_secret(settings.smtp_user)
    password = _clean_secret(settings.smtp_password)
    if not host:
        return "Email not configured (SMTP_HOST missing); alert logged only"
    return SmtpTarget(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        from_addr=from_addr,
        recipients=recipients,
        provider="smtp",
    )


async def deliver_email_alert(
    alert: ScanAlert,
    *,
    settings: Settings | None = None,
    subject_override: str | None = None,
) -> EmailDeliveryResult:
    settings = settings or get_settings()
    logger.info("email.alert title=%s\n%s", alert.title, alert.body)

    target = resolve_smtp_target(settings)
    if isinstance(target, str):
        return EmailDeliveryResult(logged=True, email_sent=False, detail=target)

    msg = EmailMessage()
    msg["Subject"] = subject_override or alert.title
    msg["From"] = target.from_addr
    msg["To"] = ", ".join(target.recipients)
    msg.set_content(alert.body)
    if alert.html_body:
        msg.add_alternative(alert.html_body, subtype="html")

    try:
        with smtplib.SMTP(target.host, target.port, timeout=15) as server:
            if target.use_tls:
                server.starttls()
            if target.username and target.password:
                server.login(target.username, target.password)
            server.send_message(msg)
    except Exception as exc:
        logger.warning("email.delivery_failed: %s", exc)
        return EmailDeliveryResult(logged=True, email_sent=False, detail=str(exc))

    logger.info("email.sent provider=%s to=%s", target.provider, target.recipients)
    return EmailDeliveryResult(logged=True, email_sent=True, detail=f"sent via {target.provider}")


__all__ = [
    "EmailDeliveryResult",
    "SmtpTarget",
    "deliver_email_alert",
    "resolve_smtp_target",
    "ses_smtp_host",
]
