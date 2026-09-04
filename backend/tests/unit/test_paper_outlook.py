"""Unit tests for paper trade time-to-target outlook."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.application.paper.outlook import build_trade_outlook


def _candle(day: int, close: float, high: float | None = None, low: float | None = None):
    c = Decimal(str(close))
    h = Decimal(str(high if high is not None else close + 1))
    lo = Decimal(str(low if low is not None else close - 1))
    return SimpleNamespace(
        symbol="INFY",
        timeframe="1d",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=day),
        open=c,
        high=h,
        low=lo,
        close=c,
        volume=1000,
    )


def test_outlook_estimates_days_when_drifting_toward_target():
    # Rising closes toward target 120 from mark ~110
    candles = [_candle(i, 90 + i) for i in range(30)]  # ends at 119
    outlook = build_trade_outlook(
        trade_id=1,
        symbol="INFY",
        direction="LONG",
        entry=Decimal("100"),
        stop=Decimal("95"),
        target=Decimal("125"),
        mark=Decimal("110"),
        candles=candles,
        now=datetime(2024, 2, 1, tzinfo=timezone.utc),
    )
    assert outlook.distance_to_target == Decimal("15")
    assert outlook.estimated_trading_days is not None
    assert outlook.estimated_trading_days > 0
    assert outlook.estimated_reach_at is not None
    assert outlook.progress_pct > 0
    assert "INFY" in outlook.summary


def test_outlook_target_already_reached():
    candles = [_candle(i, 100 + i * 0.1) for i in range(20)]
    outlook = build_trade_outlook(
        trade_id=2,
        symbol="TCS",
        direction="LONG",
        entry=Decimal("100"),
        stop=Decimal("95"),
        target=Decimal("110"),
        mark=Decimal("112"),
        candles=candles,
    )
    assert outlook.estimated_trading_days == Decimal("0")
    assert outlook.method == "target_reached"


def test_outlook_short_uses_inverted_drift():
    # Falling market helps SHORT toward target 90
    candles = [_candle(i, 110 - i * 0.5) for i in range(25)]
    outlook = build_trade_outlook(
        trade_id=3,
        symbol="RELIANCE",
        direction="SHORT",
        entry=Decimal("100"),
        stop=Decimal("105"),
        target=Decimal("90"),
        mark=Decimal("98"),
        candles=candles,
    )
    assert outlook.distance_to_target == Decimal("8")
    assert outlook.estimated_trading_days is not None
