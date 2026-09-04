"""Technical snapshot for Groww-style research tab."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.domain.market_data import Candle
from app.domain.market_data.indicators import atr, ema, macd, rsi, sma, volume_sma


def _q(value: Decimal | None, places: str = "0.01") -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _last(values: Sequence[Decimal | None]) -> Decimal | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _signal_rsi(value: Decimal | None) -> str:
    if value is None:
        return "unavailable"
    if value >= Decimal("70"):
        return "overbought"
    if value <= Decimal("30"):
        return "oversold"
    return "neutral"


def _signal_trend(price: Decimal | None, ma: Decimal | None) -> str:
    if price is None or ma is None:
        return "unavailable"
    if price > ma:
        return "bullish"
    if price < ma:
        return "bearish"
    return "neutral"


def _signal_macd(line: Decimal | None, signal: Decimal | None, hist: Decimal | None) -> str:
    if line is None or signal is None or hist is None:
        return "unavailable"
    if hist > 0 and line > signal:
        return "bullish"
    if hist < 0 and line < signal:
        return "bearish"
    return "neutral"


@dataclass(frozen=True)
class IndicatorReading:
    name: str
    value: Decimal | None
    signal: str
    detail: str


@dataclass(frozen=True)
class PivotLevels:
    pivot: Decimal
    resistance_1: Decimal
    resistance_2: Decimal
    resistance_3: Decimal
    support_1: Decimal
    support_2: Decimal
    support_3: Decimal


@dataclass(frozen=True)
class TechnicalSnapshot:
    symbol: str
    timeframe: str
    last_close: Decimal | None
    indicators: tuple[IndicatorReading, ...]
    pivots: PivotLevels | None
    volume_vs_sma: Decimal | None


def classic_pivots(candle: Candle) -> PivotLevels:
    high = candle.high
    low = candle.low
    close = candle.close
    pivot = (high + low + close) / Decimal("3")
    return PivotLevels(
        pivot=_q(pivot) or Decimal("0"),
        resistance_1=_q((Decimal("2") * pivot) - low) or Decimal("0"),
        resistance_2=_q(pivot + (high - low)) or Decimal("0"),
        resistance_3=_q(high + Decimal("2") * (pivot - low)) or Decimal("0"),
        support_1=_q((Decimal("2") * pivot) - high) or Decimal("0"),
        support_2=_q(pivot - (high - low)) or Decimal("0"),
        support_3=_q(low - Decimal("2") * (high - pivot)) or Decimal("0"),
    )


def build_technical_snapshot(symbol: str, timeframe: str, candles: Sequence[Candle]) -> TechnicalSnapshot:
    if not candles:
        return TechnicalSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            last_close=None,
            indicators=(),
            pivots=None,
            volume_vs_sma=None,
        )

    last = candles[-1]
    close = last.close
    rsi_values = rsi(candles, 14)
    sma20 = sma(candles, 20)
    sma50 = sma(candles, 50)
    sma200 = sma(candles, 200)
    ema20 = ema(candles, 20)
    ema50 = ema(candles, 50)
    macd_line, signal_line, histogram = macd(candles)
    vol_sma = volume_sma(candles, 20)
    atr_values = atr(candles, 14)

    rsi_last = _last(rsi_values)
    sma20_last = _last(sma20)
    sma50_last = _last(sma50)
    sma200_last = _last(sma200)
    ema20_last = _last(ema20)
    ema50_last = _last(ema50)
    macd_last = _last(macd_line)
    signal_last = _last(signal_line)
    hist_last = _last(histogram)
    vol_sma_last = _last(vol_sma)
    atr_last = _last(atr_values)

    volume_ratio = None
    if last.volume is not None and vol_sma_last and vol_sma_last > 0:
        volume_ratio = _q(Decimal(last.volume) / vol_sma_last)

    indicators = (
        IndicatorReading(
            name="RSI(14)",
            value=_q(rsi_last),
            signal=_signal_rsi(rsi_last),
            detail="Relative strength vs prior closes",
        ),
        IndicatorReading(
            name="MACD(12,26,9)",
            value=_q(macd_last),
            signal=_signal_macd(macd_last, signal_last, hist_last),
            detail=f"Signal {_q(signal_last)}; hist {_q(hist_last)}",
        ),
        IndicatorReading(
            name="ATR(14)",
            value=_q(atr_last),
            signal="neutral" if atr_last is not None else "unavailable",
            detail="14-day average true range (volatility)",
        ),
        IndicatorReading(
            name="SMA 20",
            value=_q(sma20_last),
            signal=_signal_trend(close, sma20_last),
            detail="Price vs 20-day SMA",
        ),
        IndicatorReading(
            name="SMA 50",
            value=_q(sma50_last),
            signal=_signal_trend(close, sma50_last),
            detail="Price vs 50-day SMA",
        ),
        IndicatorReading(
            name="SMA 200",
            value=_q(sma200_last),
            signal=_signal_trend(close, sma200_last),
            detail="Price vs 200-day SMA",
        ),
        IndicatorReading(
            name="EMA 20",
            value=_q(ema20_last),
            signal=_signal_trend(close, ema20_last),
            detail="Price vs 20-day EMA",
        ),
        IndicatorReading(
            name="EMA 50",
            value=_q(ema50_last),
            signal=_signal_trend(close, ema50_last),
            detail="Price vs 50-day EMA",
        ),
        IndicatorReading(
            name="Volume vs SMA20",
            value=volume_ratio,
            signal=(
                "high"
                if volume_ratio is not None and volume_ratio >= Decimal("1.5")
                else "low"
                if volume_ratio is not None and volume_ratio <= Decimal("0.7")
                else "neutral"
                if volume_ratio is not None
                else "unavailable"
            ),
            detail="Today volume / 20-day volume SMA",
        ),
    )

    pivots = classic_pivots(candles[-2]) if len(candles) >= 2 else classic_pivots(last)
    return TechnicalSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        last_close=_q(close),
        indicators=indicators,
        pivots=pivots,
        volume_vs_sma=volume_ratio,
    )


__all__ = [
    "IndicatorReading",
    "PivotLevels",
    "TechnicalSnapshot",
    "build_technical_snapshot",
    "classic_pivots",
]
