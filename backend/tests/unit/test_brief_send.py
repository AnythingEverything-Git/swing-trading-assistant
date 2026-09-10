from app.application.alerts.brief_send import compose_brief_alert_from_payload
from app.application.alerts.email_delivery import resolve_smtp_target
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    payload = dict(
        database_url="sqlite+aiosqlite:///:memory:",
        email_provider="ses",
        aws_ses_region="ap-south-1",
        aws_ses_smtp_username="AKIAEXAMPLE",
        aws_ses_smtp_password="smtp-secret",
        alert_from_email="alerts@example.com",
        alert_to_emails="trader@example.com",
        frontend_base_url="http://127.0.0.1:5173",
    )
    payload.update(overrides)
    return Settings(**payload)


def test_compose_brief_alert_includes_mode_and_top():
    alert = compose_brief_alert_from_payload(
        {
            "universe_name": "NIFTY_50",
            "eligible_count": 2,
            "forming_count": 1,
            "symbols_scanned": 50,
            "data_claim": "Live Upstox 1d candles",
            "ai_brief": "Bias constructive; watch INFY.",
            "top": [
                {
                    "symbol": "INFY",
                    "candidate": {
                        "direction": "LONG",
                        "entry_price": "1520",
                        "stop_loss": "1485",
                        "target": "1590",
                    },
                }
            ],
        },
        mode="morning",
        scan_run_id=42,
        frontend_base_url="http://127.0.0.1:5173",
    )
    assert "Morning brief" in alert.title
    assert "INFY" in alert.body
    assert "Bias constructive" in alert.body
    assert alert.html_body is not None
    assert "Open this scan" in (alert.html_body or "")
    assert "run=42" in (alert.html_body or "")


def test_compose_eod_brief_title():
    alert = compose_brief_alert_from_payload(
        {"universe_name": "NIFTY_500", "eligible_count": 0, "forming_count": 0, "symbols_scanned": 10},
        mode="eod",
    )
    assert alert.title.startswith("TradePilot EOD brief")


def test_ses_still_resolves_for_brief_path():
    target = resolve_smtp_target(_settings())
    assert not isinstance(target, str)
    assert target.provider == "ses"
