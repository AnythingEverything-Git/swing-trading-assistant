from datetime import datetime, timezone
from decimal import Decimal

from app.application.narrative.gemini_narrator import (
    format_currency_tokens_in_text,
    format_money_2dp,
    normalize_insight_context,
    template_insight,
    validate_grounded_bullets,
)
from app.application.narrative.insight_cache import (
    clear_insight_cache,
    get_cached_insight,
    insight_cache_key,
    put_cached_insight,
)
from app.application.research.technical_service import build_technical_snapshot, classic_pivots
from app.domain.market_data import Candle
from app.domain.market_data.indicators import macd
from app.application.narrative.gemini_narrator import InsightResult, InsightSection


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
    assert safe == ["Entry ₹1520.00 with stop ₹1485.00"]


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
    assert result.sections
    assert result.sections[0].text == "Board meeting on results"


def test_format_money_two_decimals():
    assert format_money_2dp("1520.5") == "1520.50"
    assert format_money_2dp(99) == "99.00"
    assert format_money_2dp(None) is None


def test_normalize_insight_context_money_keys():
    normalized = normalize_insight_context(
        {
            "symbol": "INFY",
            "high_52w": "1999.1",
            "setup": {"entry": 1520.5, "stop": "1485", "target": "1600.999"},
            "performance": [{"label": "1W", "change_percent": "1.2"}],
        }
    )
    assert normalized["high_52w"] == "1999.10"
    assert normalized["setup"]["entry"] == "1520.50"
    assert normalized["setup"]["stop"] == "1485.00"
    assert normalized["setup"]["target"] == "1601.00"
    assert normalized["performance"][0]["change_percent"] == "1.20"


def test_format_currency_tokens_in_text():
    assert "₹1520.50" in format_currency_tokens_in_text("Entry at 1520.5")


def test_overview_template_is_structured():
    result = template_insight(
        "overview",
        {
            "symbol": "INFY",
            "high_52w": "1999.10",
            "last_close": "1520.50",
            "setup": {"entry": "1520.50", "stop": "1485.00", "target": "1600.00", "narrative": "Breakout hold"},
        },
    )
    assert result.title.endswith("overview & setup")
    assert result.sections
    assert any(s.label == "Entry" and s.text == "₹1520.50" for s in result.sections)


def test_insight_cache_roundtrip():
    clear_insight_cache()
    context = {"symbol": "INFY", "entry": "100.00"}
    key = insight_cache_key("INFY", "overview", context)
    result = InsightResult(
        title="t",
        bullets=("a",),
        sections=(InsightSection(label="A", text="a"),),
        provider="template",
        grounded=True,
        headline="h",
    )
    put_cached_insight(key, result, ttl_seconds=60)
    cached = get_cached_insight(key)
    assert cached is not None
    assert cached.title == "t"
    # Same facts → same key even if live price differs in a discarded field
    key2 = insight_cache_key("INFY", "overview", {**context, "current_price": "101.00"})
    assert key2 == key
