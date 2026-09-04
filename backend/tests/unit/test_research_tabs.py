from datetime import datetime, timezone
from decimal import Decimal

from app.application.narrative.gemini_narrator import template_insight, validate_grounded_bullets
from app.application.research.technical_service import build_technical_snapshot, classic_pivots
from app.domain.market_data import Candle
from app.domain.market_data.indicators import macd


def _candle(day: int, close: str, high: str | None = None, low: str | None = None, volume: int = 1000):
    close_d = Decimal(close)
    return Candle(
        symbol="INFY",
        exchange="NSE",
        instrument_id=1,
        timeframe="1d",
        timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        open=close_d,
        high=Decimal(high) if high else close_d + Decimal("2"),
        low=Decimal(low) if low else close_d - Decimal("2"),
        close=close_d,
        volume=volume,
    )


def test_macd_returns_aligned_series():
    candles = [_candle(min(i + 1, 28), str(100 + i)) for i in range(40)]
    # Use February/March-like spread by shifting month via distinct timestamps
    candles = [
        Candle(
            symbol="INFY",
            exchange="NSE",
            instrument_id=1,
            timeframe="1d",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc).replace(
                month=1 + (i // 28), day=(i % 28) + 1
            ),
            open=Decimal(100 + i),
            high=Decimal(102 + i),
            low=Decimal(98 + i),
            close=Decimal(100 + i),
            volume=1000 + i,
        )
        for i in range(40)
    ]
    line, signal, hist = macd(candles)
    assert len(line) == len(candles)
    assert any(value is not None for value in line)
    assert any(value is not None for value in signal)
    assert any(value is not None for value in hist)


def test_technical_snapshot_signals():
    candles = [
        Candle(
            symbol="INFY",
            exchange="NSE",
            instrument_id=1,
            timeframe="1d",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc).replace(
                month=1 + (i // 28), day=(i % 28) + 1
            ),
            open=Decimal(100 + i),
            high=Decimal(102 + i),
            low=Decimal(98 + i),
            close=Decimal(100 + i),
            volume=1000 + i * 10,
        )
        for i in range(60)
    ]
    snapshot = build_technical_snapshot("INFY", "1d", candles)
    assert snapshot.last_close is not None
    assert snapshot.pivots is not None
    names = {item.name for item in snapshot.indicators}
    assert "RSI(14)" in names
    assert "MACD(12,26,9)" in names


def test_classic_pivots_are_ordered():
    candle = _candle(1, "100", high="110", low="90")
    pivots = classic_pivots(candle)
    assert pivots.resistance_3 >= pivots.resistance_2 >= pivots.resistance_1
    assert pivots.support_1 >= pivots.support_2 >= pivots.support_3


def test_guardrail_drops_invented_prices():
    context = {"symbol": "INFY", "entry": "1520.00", "stop": "1485.00"}
    bullets = [
        "Entry 1520.00 with stop 1485.00",
        "Target should be 9999.00 tomorrow",
    ]
    safe = validate_grounded_bullets(bullets, context)
    assert safe == ["Entry 1520.00 with stop 1485.00"]


def test_template_insight_uses_only_provided_headlines():
    result = template_insight(
        "news",
        {
            "symbol": "INFY",
            "announcements": [{"title": "Board meeting on results"}],
            "events": [],
        },
    )
    assert result.provider == "template"
    assert result.grounded is True
    assert "Board meeting on results" in result.bullets
