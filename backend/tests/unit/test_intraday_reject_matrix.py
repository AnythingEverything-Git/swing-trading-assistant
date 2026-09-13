"""Reject-reason matrix tests for ORB V1 (strategy §1 / §22 / portfolio locks)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.intraday.breakout import find_breakout_fill, validate_stop_bounds
from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1
from app.domain.intraday.eligibility import (
    clear_eligibility_caches,
    is_corporate_action_blocked,
    is_short_allowed,
    is_surveillance_blocked,
)
from app.domain.intraday.engine import screen_symbol
from app.domain.intraday.opening_range import OpeningRange
from app.domain.intraday.sizing import can_open, size_quantity
from app.domain.intraday.types import FillPlan, PortfolioState, RankedCandidate, ScreenCandidate
from app.domain.market_data import Candle

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 9, 7)


def _bar(minute: int, o: str, h: str, l: str, c: str, vol: int = 2000) -> Candle:
    return Candle(
        symbol="AAA",
        exchange="TEST",
        instrument_id=None,
        timeframe="1m",
        timestamp=datetime(DAY.year, DAY.month, DAY.day, 9, minute, tzinfo=IST),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=vol,
    )


def _or_bars(*, bullish: bool = True) -> list[Candle]:
    # 09:15–09:19 complete OR
    if bullish:
        return [
            _bar(15, "100", "100.5", "99.8", "100.2", 2000),
            _bar(16, "100.2", "100.6", "100.0", "100.4", 2000),
            _bar(17, "100.4", "100.8", "100.2", "100.6", 2000),
            _bar(18, "100.6", "101.0", "100.4", "100.8", 2000),
            _bar(19, "100.8", "101.2", "100.6", "101.0", 2000),
        ]
    # Flat / doji body
    return [
        _bar(15, "100", "100.1", "99.9", "100.0", 2000),
        _bar(16, "100.0", "100.1", "99.95", "100.02", 2000),
        _bar(17, "100.02", "100.08", "99.98", "100.01", 2000),
        _bar(18, "100.01", "100.05", "99.97", "100.0", 2000),
        _bar(19, "100.0", "100.04", "99.96", "100.01", 2000),
    ]


def _daily_atr_series() -> list[Candle]:
    """Enough prior daily bars for ATR14."""
    out: list[Candle] = []
    base = datetime(DAY.year, DAY.month, DAY.day, 15, 30, tzinfo=IST) - timedelta(days=40)
    px = Decimal("100")
    for i in range(30):
        ts = base + timedelta(days=i)
        if ts.weekday() >= 5:
            continue
        out.append(
            Candle(
                symbol="AAA",
                exchange="TEST",
                instrument_id=None,
                timeframe="1d",
                timestamp=ts,
                open=px,
                high=px + Decimal("2"),
                low=px - Decimal("2"),
                close=px + Decimal("1"),
                volume=1_000_000,
            )
        )
        px += Decimal("1")
    return out


def _screen(**kwargs):
    defaults = dict(
        symbol="AAA",
        instrument_id="AAA",
        session_date=DAY,
        candles_1m=_or_bars(bullish=True),
        prior_first_5m_volumes=[1000] * 14,
        daily_candles=_daily_atr_series(),
        adv_value=Decimal("100000000"),
        short_allowed=True,
        surveillance_blocked=False,
        corporate_action_blocked=False,
        spread=Decimal("0.05"),
        mid_price=Decimal("101"),
        tick_size=Decimal("0.05"),
        asset_class="STOCK",
        config=DEFAULT_CONFIG_V1,
    )
    defaults.update(kwargs)
    return screen_symbol(**defaults)


def _orng(symbol: str = "AAA") -> OpeningRange:
    return OpeningRange(
        symbol=symbol,
        session_date=DAY,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99.5"),
        close=Decimal("100.8"),
        volume=5000,
        bar_open=datetime(DAY.year, DAY.month, DAY.day, 9, 15, tzinfo=IST),
    )


def _fill(symbol: str = "AAA", risk: str = "10000") -> FillPlan:
    now = datetime(DAY.year, DAY.month, DAY.day, 9, 25, tzinfo=IST)
    return FillPlan(
        symbol=symbol,
        direction="LONG",
        rank=1,
        entry=Decimal("101.1"),
        stop=Decimal("100.35"),
        quantity=100,
        stop_distance=Decimal("0.75"),
        effective_risk_per_share=Decimal("0.75"),
        trigger_bar_open=now,
        risk_amount=Decimal(risk),
    )


def test_surveillance_blocked():
    _, result = _screen(surveillance_blocked=True)
    assert result.reason == "SURVEILLANCE_BLOCKED"


def test_corporate_action_block():
    _, result = _screen(corporate_action_blocked=True)
    assert result.reason == "CORPORATE_ACTION_BLOCK"


def test_spread_too_wide():
    _, result = _screen(spread=Decimal("0.5"), mid_price=Decimal("101"))
    assert result.reason == "SPREAD_TOO_WIDE"


def test_insufficient_history_missing_or():
    _, result = _screen(candles_1m=[])
    assert result.reason == "INSUFFICIENT_HISTORY"


def test_doji_direction():
    _, result = _screen(candles_1m=_or_bars(bullish=False))
    assert result.reason == "DOJI"


def test_short_not_permitted_when_or_bearish():
    # Force SHORT OR then deny short
    bars = [
        _bar(15, "100", "100.2", "98.5", "98.8", 2000),
        _bar(16, "98.8", "99.0", "98.0", "98.2", 2000),
        _bar(17, "98.2", "98.4", "97.5", "97.8", 2000),
        _bar(18, "97.8", "98.0", "97.0", "97.2", 2000),
        _bar(19, "97.2", "97.4", "96.5", "96.8", 2000),
    ]
    _, result = _screen(candles_1m=bars, short_allowed=False)
    assert result.reason == "SHORT_NOT_PERMITTED"


def test_insufficient_history_rvol_lookback():
    _, result = _screen(prior_first_5m_volumes=[1000] * 10)
    assert result.reason == "INSUFFICIENT_HISTORY"


def test_insufficient_rvol():
    # OR volume ~10000; priors mean 50000 → rvol ≈ 0.2 < min_rvol5 (1.0)
    _, result = _screen(prior_first_5m_volumes=[50000] * 14)
    assert result.reason == "INSUFFICIENT_RVOL"


def test_insufficient_liquidity():
    _, result = _screen(adv_value=Decimal("1000"))
    assert result.reason == "INSUFFICIENT_LIQUIDITY"


def test_ranked_armed_happy_path():
    cand, result = _screen()
    assert cand is not None
    assert result.reason == "RANKED_ARMED"
    assert result.direction == "LONG"


def test_eligibility_helpers():
    clear_eligibility_caches()
    assert is_short_allowed("NIFTYBEES") is False
    assert is_short_allowed("RELIANCE") is True
    assert isinstance(is_surveillance_blocked("RELIANCE", session_date=DAY), bool)
    assert isinstance(is_corporate_action_blocked("RELIANCE", DAY), bool)


def test_portfolio_locks():
    equity = Decimal("1000000")
    state = PortfolioState(equity=equity)

    state.traded_symbols.add("AAA")
    assert can_open(state, _fill("AAA"), DEFAULT_CONFIG_V1) == "ORDER_REJECTED"
    state.traded_symbols.clear()

    state.realized_pnl = -(equity * DEFAULT_CONFIG_V1.daily_loss_lock_pct)
    assert can_open(state, _fill(), DEFAULT_CONFIG_V1) == "DAILY_LOSS_LOCK"
    state.realized_pnl = Decimal("0")

    state.consecutive_losses = DEFAULT_CONFIG_V1.consecutive_loss_lock
    assert can_open(state, _fill(), DEFAULT_CONFIG_V1) == "CONSECUTIVE_LOSS_LOCK"
    state.consecutive_losses = 0

    assert can_open(state, _fill(risk=str(equity)), DEFAULT_CONFIG_V1) == "PORTFOLIO_RISK_LIMIT"

    for i in range(DEFAULT_CONFIG_V1.max_concurrent):
        state.open_fills.append(_fill(symbol=f"S{i}", risk="1000"))
    assert can_open(state, _fill("NEW", risk="1000"), DEFAULT_CONFIG_V1) == "PORTFOLIO_RISK_LIMIT"


def test_size_quantity_caps():
    qty = size_quantity(
        equity=Decimal("1000000"),
        effective_risk_per_share=Decimal("10"),
        entry=Decimal("100"),
        config=DEFAULT_CONFIG_V1,
    )
    assert qty > 0
    assert (
        size_quantity(
            equity=Decimal("1000000"),
            effective_risk_per_share=Decimal("0"),
            entry=Decimal("100"),
        )
        == 0
    )


def test_breakout_not_triggered():
    cand = ScreenCandidate(
        symbol="AAA",
        instrument_id="AAA",
        direction="LONG",
        opening_range=_orng(),
        rvol5=Decimal("2"),
        adv_value=Decimal("100000000"),
        prior_atr14=Decimal("7.5"),
        spread=Decimal("0.05"),
        tick_size=Decimal("0.05"),
    )
    ranked = RankedCandidate(candidate=cand, rank=1)
    bars = [
        Candle(
            symbol="AAA",
            exchange="TEST",
            instrument_id=None,
            timeframe="1m",
            timestamp=datetime(DAY.year, DAY.month, DAY.day, 9, 21, tzinfo=IST),
            open=Decimal("100.5"),
            high=Decimal("100.8"),
            low=Decimal("100.4"),
            close=Decimal("100.6"),
            volume=1000,
        )
    ]
    assert find_breakout_fill(ranked, bars, DAY) is None


def test_risk_invalid_stop_bounds():
    err = validate_stop_bounds(
        entry=Decimal("101.1"),
        stop_distance=Decimal("0.01"),
        opening_range=_orng(),
        spread=Decimal("0.05"),
        tick=Decimal("0.05"),
        config=DEFAULT_CONFIG_V1,
    )
    assert err is not None
    assert "stop" in err.lower()
    # Engine maps this detail to RISK_INVALID on fill planning
