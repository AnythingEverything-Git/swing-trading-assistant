from datetime import datetime, timezone
from decimal import Decimal

from app.domain.market_data.indicators import atr, ema, rsi, sma, volume_sma
from app.domain.market_data import Candle


def make_candle(symbol: str, timestamp: datetime, close: str, high: str | None = None, low: str | None = None, volume: int | None = 1000) -> Candle:
    close_dec = Decimal(close)
    high_dec = Decimal(high) if high is not None else close_dec + Decimal("2")
    low_dec = Decimal(low) if low is not None else close_dec - Decimal("2")
    return Candle(
        symbol=symbol,
        exchange="TEST",
        instrument_id=1,
        timeframe="1d",
        timestamp=timestamp,
        open=close_dec - Decimal("1"),
        high=high_dec,
        low=low_dec,
        close=close_dec,
        volume=volume,
    )


def test_sma_normal_case():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12"),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "14"),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "16"),
    ]

    result = sma(candles, 2)
    assert result[0] is None
    assert result[1] == Decimal("11")
    assert result[2] == Decimal("13")
    assert result[3] == Decimal("15")


def test_sma_insufficient_data():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12"),
    ]

    result = sma(candles, 3)
    assert result == [None, None]


def test_ema_normal_case():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12"),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "14"),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "16"),
    ]

    result = ema(candles, 3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] == Decimal("12")
    assert result[3] == Decimal("14")


def test_ema_insufficient_data():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12"),
    ]

    result = ema(candles, 3)
    assert result == [None, None]


def test_rsi_normal_case():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "11"),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "11"),
        make_candle("TST", datetime(2020, 1, 5, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 6, tzinfo=timezone.utc), "9"),
        make_candle("TST", datetime(2020, 1, 7, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 8, tzinfo=timezone.utc), "11"),
        make_candle("TST", datetime(2020, 1, 9, tzinfo=timezone.utc), "12"),
    ]

    result = rsi(candles, 3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] is None
    assert result[3] == Decimal("66.66666666666666666666666667")
    assert result[4] == Decimal("44.44444444444444444444444444")


def test_rsi_insufficient_data():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "11"),
    ]

    result = rsi(candles, 3)
    assert result == [None, None]


def test_rsi_all_gains_and_losses():
    gains = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "11"),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "12"),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "13"),
    ]
    losses = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "13"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12"),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "11"),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "10"),
    ]

    assert rsi(gains, 2)[3] == Decimal("100")
    assert rsi(losses, 2)[3] == Decimal("0")


def test_atr_normal_case():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10", high="12", low="9"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12", high="14", low="10"),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "11", high="13", low="9"),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "13", high="15", low="11"),
    ]

    result = atr(candles, 2)
    assert result[0] is None
    assert result[1] == Decimal("3.5")
    assert result[2] == Decimal("3.75")
    assert result[3] == Decimal("3.875")


def test_atr_insufficient_data():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10", high="12", low="9"),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12", high="14", low="10"),
    ]

    result = atr(candles, 3)
    assert result == [None, None]


def test_volume_sma():
    candles = [
        make_candle("TST", datetime(2020, 1, 1, tzinfo=timezone.utc), "10", volume=10),
        make_candle("TST", datetime(2020, 1, 2, tzinfo=timezone.utc), "12", volume=20),
        make_candle("TST", datetime(2020, 1, 3, tzinfo=timezone.utc), "14", volume=30),
        make_candle("TST", datetime(2020, 1, 4, tzinfo=timezone.utc), "16", volume=40),
    ]

    result = volume_sma(candles, 2)
    assert result[0] is None
    assert result[1] == Decimal("15")
    assert result[2] == Decimal("25")
    assert result[3] == Decimal("35")
