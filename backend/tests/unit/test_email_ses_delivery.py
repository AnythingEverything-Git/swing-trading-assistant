from app.application.alerts.email_delivery import resolve_smtp_target, ses_smtp_host
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    payload = dict(
        database_url="sqlite+aiosqlite:///:memory:",
        email_provider="ses",
        aws_ses_region="ap-south-1",
        aws_ses_smtp_username="AKIAEXAMPLE",
        aws_ses_smtp_password="smtp-secret",
        alert_from_email="alerts@example.com",
        alert_to_emails="trader@example.com, other@example.com",
    )
    payload.update(overrides)
    return Settings(**payload)


def test_ses_smtp_host_uses_region():
    assert ses_smtp_host("us-east-1") == "email-smtp.us-east-1.amazonaws.com"


def test_ses_target_defaults_host_from_region():
    target = resolve_smtp_target(_settings())
    assert not isinstance(target, str)
    assert target.provider == "ses"
    assert target.host == "email-smtp.ap-south-1.amazonaws.com"
    assert target.port == 587
    assert target.use_tls is True
    assert target.username == "AKIAEXAMPLE"
    assert target.recipients == ("trader@example.com", "other@example.com")


def test_ses_missing_credentials_does_not_send():
    detail = resolve_smtp_target(_settings(aws_ses_smtp_username="", aws_ses_smtp_password=""))
    assert isinstance(detail, str)
    assert "SES SMTP credentials missing" in detail


def test_ses_missing_from_or_to_does_not_send():
    detail = resolve_smtp_target(_settings(alert_from_email="", alert_to_emails=""))
    assert isinstance(detail, str)
    assert "ALERT_FROM_EMAIL" in detail
