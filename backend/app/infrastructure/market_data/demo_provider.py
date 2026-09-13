"""Deterministic demo market-data provider for development without Upstox.

Generates realistic 1d OHLCV series from a symbol-derived seed. Also supports
synthetic `1m` / `5m` session bars (IST) for intraday ORB MVP demos.
Independent of live vendors. Explicitly instantiable; not a silent production replacement.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, List, Sequence
from zoneinfo import ZoneInfo

from app.domain.market_data import Candle
from app.domain.market_data.provider import MarketDataProvider

_IST = ZoneInfo("Asia/Kolkata")

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
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must be a non-empty string")

        if timeframe == "1d":
            return self._daily_candles(normalized, start, end)
        if timeframe in {"1m", "5m"}:
            candles_1m = self._minute_candles(normalized, start, end)
            if timeframe == "1m":
                return candles_1m
            return _aggregate_5m(candles_1m)
        raise ValueError("DemoMarketDataProvider supports timeframes '1d', '1m', '5m'")

    async def get_last_traded_prices(self, symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Synthetic LTP from the latest demo daily close (desk works offline)."""
        names = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not names:
            return {}
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=40)
        out: dict[str, dict[str, Any]] = {}
        for symbol in names:
            candles = await self.get_candles(symbol, "1d", start, end)
            if len(candles) < 1:
                continue
            last = candles[-1]
            prev = candles[-2] if len(candles) >= 2 else last
            net = last.close - prev.close
            out[symbol] = {
                "last_price": last.close,
                "instrument_key": f"DEMO:{symbol}",
                "raw": {"net_change": net, "symbol": symbol},
            }
        return out

    async def get_option_chain(self, symbol: str, expiry_date: str = "current_month") -> dict[str, Any]:
        """Deterministic near-ATM demo option chain for research F&O tab."""
        normalized = symbol.strip().upper()
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=40)
        candles = await self.get_candles(normalized, "1d", start, end)
        spot = candles[-1].close if candles else Decimal("100")
        seed = self.symbol_seed(normalized)
        step = Decimal("5") if spot < 500 else Decimal("10") if spot < 2000 else Decimal("50")
        atm = (spot / step).to_integral_value(rounding=ROUND_HALF_UP) * step
        rows: list[dict[str, Any]] = []
        for i in range(-10, 11):
            strike = atm + step * Decimal(i)
            dist = abs(i)
            call_oi = Decimal(50_000 + (seed % 7_000) - dist * 2_000)
            put_oi = Decimal(48_000 + (seed % 5_000) - dist * 1_800)
            intrinsic_c = max(Decimal("0"), spot - strike)
            intrinsic_p = max(Decimal("0"), strike - spot)
            time_val = Decimal("2") + Decimal(max(0, 8 - dist)) * Decimal("0.35")
            rows.append(
                {
                    "strike": strike,
                    "call_ltp": (intrinsic_c + time_val).quantize(Decimal("0.05")),
                    "call_oi": max(Decimal("1000"), call_oi),
                    "call_iv": Decimal("18") + Decimal(dist),
                    "call_oi_change": Decimal(1000 - dist * 50),
                    "put_ltp": (intrinsic_p + time_val).quantize(Decimal("0.05")),
                    "put_oi": max(Decimal("1000"), put_oi),
                    "put_iv": Decimal("19") + Decimal(dist),
                    "put_oi_change": Decimal(800 - dist * 40),
                }
            )
        total_call = sum((Decimal(str(r["call_oi"])) for r in rows), Decimal("0"))
        total_put = sum((Decimal(str(r["put_oi"])) for r in rows), Decimal("0"))
        pcr = (total_put / total_call).quantize(Decimal("0.0001")) if total_call else None
        return {
            "symbol": normalized,
            "expiry": expiry_date,
            "spot": spot,
            "pcr": pcr,
            "futures_ltp": spot + Decimal("0.5"),
            "futures_premium": Decimal("0.5"),
            "futures_premium_status": "ok",
            "rows": rows,
        }

    def _daily_candles(self, normalized: str, start: datetime, end: datetime) -> List[Candle]:
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

    def _minute_candles(self, normalized: str, start: datetime, end: datetime) -> List[Candle]:
        start_ist = start.astimezone(_IST) if start.tzinfo else start.replace(tzinfo=timezone.utc).astimezone(_IST)
        end_ist = end.astimezone(_IST) if end.tzinfo else end.replace(tzinfo=timezone.utc).astimezone(_IST)
        days = _weekday_dates(start_ist.date(), end_ist.date())
        seed = self.symbol_seed(normalized)
        base = Decimal(100 + (seed % 400)) + (Decimal(seed % 100) / Decimal(100))
        out: list[Candle] = []
        for day in days:
            out.extend(_generate_session_1m(normalized, day, base, seed))
        # Clip to requested window
        return [c for c in out if start <= c.timestamp <= end]


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


def _relative_return(regime: str, rng: _LCG) -> Decimal:
    """Daily simple return with r > -1 so price * (1 + r) stays strictly positive.

    Magnitudes mirror the former absolute drifts near a ~100 reference level,
    but scale with price so long downtrends cannot cross or approach zero.
    """
    if regime == "uptrend":
        return Decimal("0.0035") + Decimal(str(rng.uniform() * 0.0025))
    if regime == "downtrend":
        return Decimal("-0.0035") - Decimal(str(rng.uniform() * 0.0025))
    if regime == "sideways":
        return Decimal(str(rng.uniform_signed() * 0.0015))
    # choppy / default — larger swings, still bounded away from -100%
    return Decimal(str(rng.uniform_signed() * 0.012))


def _ohlc_from_open_close(
    open_p: Decimal,
    close_p: Decimal,
    wick_frac: Decimal,
    volume: int,
) -> tuple[Decimal, Decimal, Decimal, Decimal, int]:
    """Build OHLC from positive open/close and a proportional wick fraction.

    Requires open_p > 0, close_p > 0, and 0 <= wick_frac < 1. Low is then
    min(open, close) * (1 - wick_frac) > 0 by construction (before quantize).
    """
    body_low = min(open_p, close_p)
    body_high = max(open_p, close_p)
    # Keep wick strictly inside the body so low cannot reach zero.
    safe_frac = wick_frac if wick_frac < Decimal("1") else Decimal("0.25")
    if safe_frac < 0:
        safe_frac = Decimal("0")
    wick = body_low * safe_frac
    high = body_high + wick
    low = body_low - wick
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
        ret = _relative_return(regime, rng)
        open_p = price
        # Multiplicative update: positive price and ret > -1 ⇒ close_p > 0.
        close_p = price * (Decimal("1") + ret)
        wick_frac = Decimal("0.002") + Decimal(str(rng.uniform() * 0.004))
        vol = base_volume + int(rng.uniform() * 400) + (index % 7) * 10
        levels.append(_ohlc_from_open_close(open_p, close_p, wick_frac, vol))
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


def _weekday_dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _generate_session_1m(
    symbol: str,
    day: date,
    base: Decimal,
    seed: int,
) -> list[Candle]:
    """Synthetic NSE cash session 09:15–15:29 IST.

    ORB-friendly path: bullish OR, then breakout after 09:20 for most seeds.
    """
    rng = _LCG(seed ^ (day.toordinal() * 2654435761 & 0xFFFFFFFF))
    price = base * (Decimal("1") + Decimal(str((rng.uniform_signed()) * 0.01)))
    candles: list[Candle] = []
    # High OR volume for stocks-in-play demos when symbol hash even
    or_vol_boost = 8 if (seed % 2 == 0 or symbol.startswith("ORB")) else 2

    minute = datetime(day.year, day.month, day.day, 9, 15, tzinfo=_IST)
    session_end = datetime(day.year, day.month, day.day, 15, 30, tzinfo=_IST)
    bar_i = 0
    or_high = price
    while minute < session_end:
        in_or = minute.hour == 9 and minute.minute < 20
        # Bullish OR: drift up during first 5 minutes
        if in_or:
            ret = Decimal("0.0008") + Decimal(str(rng.uniform() * 0.0004))
            vol = int(5000 * or_vol_boost + rng.uniform() * 500)
        elif bar_i == 5:
            # First post-OR bar: mild break above OR high (avoid huge gap → RISK_INVALID)
            ret = Decimal("0.0015")
            vol = int(3000 + rng.uniform() * 800)
        else:
            ret = Decimal(str(rng.uniform_signed() * 0.0006))
            vol = int(800 + rng.uniform() * 400)

        open_p = price
        close_p = price * (Decimal("1") + ret)
        if bar_i == 5 and not in_or:
            # Trade through OR high without gap-open far above it
            open_p = min(open_p, or_high)
            close_p = max(close_p, or_high + Decimal("0.10"))
            high = max(close_p, or_high + Decimal("0.15"))
            low = min(open_p, or_high - Decimal("0.05"))
            wick = Decimal("0")
        else:
            wick = abs(close_p - open_p) * Decimal("0.15") + Decimal("0.05")
            high = max(open_p, close_p) + wick
            low = min(open_p, close_p) - wick
            if low <= 0:
                low = min(open_p, close_p) * Decimal("0.999")

        if in_or:
            or_high = max(or_high, high)

        if bar_i == 5 and not in_or:
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange="DEMO",
                    instrument_id=None,
                    timeframe="1m",
                    timestamp=minute,
                    open=_quantize(open_p),
                    high=_quantize(high),
                    low=_quantize(max(Decimal("0.01"), low)),
                    close=_quantize(close_p),
                    volume=max(1, vol),
                )
            )
            price = close_p
            minute += timedelta(minutes=1)
            bar_i += 1
            continue

        candles.append(
            Candle(
                symbol=symbol,
                exchange="DEMO",
                instrument_id=None,
                timeframe="1m",
                timestamp=minute,
                open=_quantize(open_p),
                high=_quantize(high),
                low=_quantize(low),
                close=_quantize(close_p),
                volume=max(1, vol),
            )
        )
        price = close_p
        minute += timedelta(minutes=1)
        bar_i += 1
    return candles


def _aggregate_5m(candles_1m: Sequence[Candle]) -> list[Candle]:
    if not candles_1m:
        return []
    out: list[Candle] = []
    bucket: list[Candle] = []
    for candle in candles_1m:
        ts = candle.timestamp.astimezone(_IST)
        # Bucket by floor to 5 minutes from 09:15
        bucket.append(candle)
        if len(bucket) == 5 or (
            bucket and ts.minute % 5 == 4
        ):
            if len(bucket) >= 1:
                first, last = bucket[0], bucket[-1]
                out.append(
                    Candle(
                        symbol=first.symbol,
                        exchange=first.exchange,
                        instrument_id=first.instrument_id,
                        timeframe="5m",
                        timestamp=first.timestamp,
                        open=first.open,
                        high=max(c.high for c in bucket),
                        low=min(c.low for c in bucket),
                        close=last.close,
                        volume=sum(int(c.volume or 0) for c in bucket),
                    )
                )
            bucket = []
    if bucket:
        first, last = bucket[0], bucket[-1]
        out.append(
            Candle(
                symbol=first.symbol,
                exchange=first.exchange,
                instrument_id=first.instrument_id,
                timeframe="5m",
                timestamp=first.timestamp,
                open=first.open,
                high=max(c.high for c in bucket),
                low=min(c.low for c in bucket),
                close=last.close,
                volume=sum(int(c.volume or 0) for c in bucket),
            )
        )
    return out


__all__ = ["DemoMarketDataProvider", "create_demo_market_data_provider"]
