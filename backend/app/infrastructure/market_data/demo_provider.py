"""Deterministic demo market-data provider for development without Upstox.

Generates realistic 1d OHLCV series from a symbol-derived seed. Independent of
live vendors. Explicitly instantiable; not a silent production replacement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Sequence

from app.domain.market_data import Candle
from app.domain.market_data.provider import MarketDataProvider

# First 22 bars of the known Breakout->Retest->Confirmation fixture (confirmation on last bar).
# Used only as a price/volume pattern; the strategy still decides eligibility.
_BREAKOUT_SETUP_TAIL: tuple[tuple[float, float, float, float, int], ...] = (
    (97.0, 97.5, 96.5, 96.8, 1200),
    (98.0, 98.9, 97.2, 97.6, 1200),
    (99.0, 99.8, 98.0, 98.4, 1200),
    (99.5, 100.0, 98.8, 99.3, 1200),
    (100.2, 100.6, 99.5, 99.9, 1200),
    (100.8, 101.5, 99.7, 100.6, 1300),
    (99.8, 100.3, 98.9, 99.2, 1300),
    (98.9, 99.2, 97.8, 98.5, 1300),
    (98.7, 99.0, 97.9, 98.2, 1200),
    (99.2, 99.6, 98.5, 98.9, 1200),
    (98.8, 99.3, 98.0, 98.5, 1200),
    (99.4, 99.9, 98.8, 99.1, 1200),
    (99.0, 99.4, 98.2, 98.6, 1200),
    (98.6, 98.9, 97.7, 98.3, 1200),
    (99.4, 99.8, 98.9, 99.1, 1200),
    (100.0, 100.3, 99.2, 99.6, 1400),
    (99.4, 99.8, 98.5, 98.9, 1300),
    (100.4, 101.0, 99.7, 100.2, 1300),
    (99.6, 100.0, 98.8, 99.2, 1300),
    (101.8, 102.2, 100.6, 101.1, 2000),
    (100.9, 101.0, 100.1, 100.5, 1500),
    (101.8, 102.2, 100.7, 101.2, 2200),
)

_EXPLICIT_REGIMES: dict[str, str] = {
    "DEMO_SETUP": "breakout_setup",
    "DEMO_SIDEWAYS": "sideways",
    "DEMO_TREND": "uptrend",
    "DEMO_CHOP": "choppy",
    "DEMO_DOWN": "downtrend",
}

_REGIME_BY_BUCKET: tuple[str, ...] = (
    "breakout_setup",
    "uptrend",
    "sideways",
    "choppy",
    "downtrend",
)


def _fnv1a32(text: str) -> int:
    """Stable 32-bit FNV-1a hash (not Python's randomized hash())."""
    h = 2166136261
    for char in text.encode("utf-8"):
        h ^= char
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class _LCG:
    """Deterministic linear congruential generator."""

    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFF

    def next_u32(self) -> int:
        self._state = (1664525 * self._state + 1013904223) & 0xFFFFFFFF
        return self._state

    def uniform(self) -> float:
        return self.next_u32() / 4294967296.0

    def uniform_signed(self) -> float:
        return self.uniform() * 2.0 - 1.0


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic demo OHLCV source for development and North-Star demos.

    Instantiate explicitly (e.g. in scripts/tests). Does not replace Upstox in
    production application wiring.
    """

    exchange = "DEMO"

    def __init__(self) -> None:
        pass

    @staticmethod
    def symbol_seed(symbol: str) -> int:
        return _fnv1a32(symbol.strip().upper())

    @staticmethod
    def regime_for_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized in _EXPLICIT_REGIMES:
            return _EXPLICIT_REGIMES[normalized]
        return _REGIME_BY_BUCKET[DemoMarketDataProvider.symbol_seed(normalized) % len(_REGIME_BY_BUCKET)]

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        if start is None or end is None:
            raise ValueError("start and end required")
        if start > end:
            raise ValueError("start must be <= end")
        if timeframe != "1d":
            raise ValueError("DemoMarketDataProvider only supports timeframe '1d'")

        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must be a non-empty string")

        start_ts = _as_utc(start)
        end_ts = _as_utc(end)
        dates = _daily_timestamps(start_ts, end_ts)
        if not dates:
            return []

        seed = self.symbol_seed(normalized)
        regime = self.regime_for_symbol(normalized)
        base = Decimal(50 + (seed % 450)) + (Decimal(seed % 100) / Decimal(100))
        rng = _LCG(seed ^ 0xA5A5A5A5)

        if regime == "breakout_setup" and len(dates) >= len(_BREAKOUT_SETUP_TAIL):
            levels = _generate_with_setup_tail(dates, base, rng)
        else:
            levels = _generate_regime_walk(dates, base, regime, rng)

        return [
            Candle(
                symbol=normalized,
                exchange=self.exchange,
                instrument_id=None,
                timeframe="1d",
                timestamp=ts,
                open=ohlc[0],
                high=ohlc[1],
                low=ohlc[2],
                close=ohlc[3],
                volume=ohlc[4],
            )
            for ts, ohlc in zip(dates, levels)
        ]


def create_demo_market_data_provider() -> DemoMarketDataProvider:
    """Explicit constructor for scripts/tests — not used by production Upstox wiring."""
    return DemoMarketDataProvider()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _daily_timestamps(start: datetime, end: datetime) -> list[datetime]:
    cur = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    last = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    out: list[datetime] = []
    while cur <= last:
        out.append(cur)
        cur = cur + timedelta(days=1)
    return out


def _ohlc_from_open_close(open_p: Decimal, close_p: Decimal, wick: Decimal, volume: int) -> tuple[Decimal, Decimal, Decimal, Decimal, int]:
    high = max(open_p, close_p) + wick
    low = min(open_p, close_p) - wick
    if low <= 0:
        low = min(open_p, close_p) * Decimal("0.5")
        if low <= 0:
            low = Decimal("0.01")
    return (
        _quantize(open_p),
        _quantize(high),
        _quantize(low),
        _quantize(close_p),
        max(1, int(volume)),
    )


def _generate_regime_walk(
    dates: Sequence[datetime],
    base: Decimal,
    regime: str,
    rng: _LCG,
) -> list[tuple[Decimal, Decimal, Decimal, Decimal, int]]:
    levels: list[tuple[Decimal, Decimal, Decimal, Decimal, int]] = []
    price = base
    base_volume = 1000 + (int(base) % 500)

    for index in range(len(dates)):
        if regime == "uptrend":
            drift = Decimal("0.35") + Decimal(str(rng.uniform() * 0.25))
        elif regime == "downtrend":
            drift = Decimal("-0.35") - Decimal(str(rng.uniform() * 0.25))
        elif regime == "sideways":
            drift = Decimal(str(rng.uniform_signed() * 0.15))
        else:  # choppy / default
            drift = Decimal(str(rng.uniform_signed() * 1.2))

        open_p = price
        close_p = price + drift
        if close_p <= 0:
            close_p = Decimal("0.50")
        wick = Decimal("0.20") + Decimal(str(rng.uniform() * 0.40))
        vol = base_volume + int(rng.uniform() * 400) + (index % 7) * 10
        levels.append(_ohlc_from_open_close(open_p, close_p, wick, vol))
        price = close_p

    return levels


def _generate_with_setup_tail(
    dates: Sequence[datetime],
    base: Decimal,
    rng: _LCG,
) -> list[tuple[Decimal, Decimal, Decimal, Decimal, int]]:
    tail_len = len(_BREAKOUT_SETUP_TAIL)
    warmup_len = len(dates) - tail_len
    scale = base / Decimal("100")

    warmup = _generate_regime_walk(dates[:warmup_len], base, "sideways", rng) if warmup_len > 0 else []
    if warmup:
        # Anchor pattern scale so first setup open continues near warmup close.
        anchor = warmup[-1][3]
        scale = anchor / Decimal(str(_BREAKOUT_SETUP_TAIL[0][0]))

    tail: list[tuple[Decimal, Decimal, Decimal, Decimal, int]] = []
    for open_, high, low, close, volume in _BREAKOUT_SETUP_TAIL:
        tail.append(
            (
                _quantize(Decimal(str(open_)) * scale),
                _quantize(Decimal(str(high)) * scale),
                _quantize(Decimal(str(low)) * scale),
                _quantize(Decimal(str(close)) * scale),
                max(1, int(volume)),
            )
        )
    return warmup + tail


__all__ = ["DemoMarketDataProvider", "create_demo_market_data_provider"]
