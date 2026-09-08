"""Unit tests for intraday ORB V1 domain engine + demo session."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.application.intraday.session_service import run_demo_session, session_report_to_dict
from app.domain.intraday.breakout import find_breakout_fill, validate_stop_bounds
from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1
from app.domain.intraday.opening_range import build_opening_range, direction_from_or
from app.domain.intraday.rank import rank_candidates
from app.domain.intraday.rvol import compute_rvol5
from app.domain.intraday.types import OpeningRange, ScreenCandidate
from app.domain.market_data import Candle
from app.infrastructure.market_data.demo_provider import DemoMarketDataProvider

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 9, 7)


def _c(symbol: str, minute: int, o: str, h: str, l: str, c: str, vol: int = 1000) -> Candle:
    ts = datetime(DAY.year, DAY.month, DAY.day, 9, minute, tzinfo=IST)
    return Candle(
        symbol=symbol,
        exchange="TEST",
        instrument_id=None,
        timeframe="1m",
        timestamp=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=vol,
    )


def test_opening_range_and_doji():
    bars = [
        _c("AAA", 15, "100", "100.5", "99.8", "100.2", 1000),
        _c("AAA", 16, "100.2", "100.6", "100.0", "100.4", 1000),
        _c("AAA", 17, "100.4", "100.8", "100.2", "100.6", 1000),
        _c("AAA", 18, "100.6", "101.0", "100.4", "100.8", 1000),
        _c("AAA", 19, "100.8", "101.2", "100.6", "101.0", 1000),
    ]
    orng = build_opening_range("AAA", DAY, bars)
    assert orng is not None
    assert orng.open == Decimal("100")
    assert orng.close == Decimal("101.0")
    assert direction_from_or(orng, Decimal("0.05")) == "LONG"

    doji = OpeningRange(
        symbol="AAA",
        session_date=DAY,
        open=Decimal("100"),
        high=Decimal("100.2"),
        low=Decimal("99.9"),
        close=Decimal("100.02"),
        volume=100,
        bar_open=bars[0].timestamp,
    )
    assert direction_from_or(doji, Decimal("0.05")) is None


def test_rvol_requires_14_sessions():
    assert compute_rvol5(1000, [100] * 13) is None
    rvol = compute_rvol5(2000, [1000] * 14)
    assert rvol == Decimal("2")


def test_rank_is_deterministic():
    def cand(sym: str, rvol: str, exp: str, adv: str) -> ScreenCandidate:
        orng = OpeningRange(
            symbol=sym,
            session_date=DAY,
            open=Decimal("100"),
            high=Decimal("100") + Decimal(exp),
            low=Decimal("100"),
            close=Decimal("100.5"),
            volume=1000,
            bar_open=datetime(DAY.year, DAY.month, DAY.day, 9, 15, tzinfo=IST),
        )
        return ScreenCandidate(
            symbol=sym,
            instrument_id=sym,
            direction="LONG",
            opening_range=orng,
            rvol5=Decimal(rvol),
            adv_value=Decimal(adv),
            prior_atr14=Decimal("5"),
        )

    ranked = rank_candidates(
        [cand("B", "2", "1", "10"), cand("A", "2", "1", "10"), cand("C", "3", "1", "10")],
        DEFAULT_CONFIG_V1,
    )
    assert [r.candidate.symbol for r in ranked] == ["C", "A", "B"]


def test_rank_candidates_split_stocks_and_etfs():
    from app.domain.intraday.rank import rank_candidates_split

    def cand(sym: str, rvol: str, asset: str) -> ScreenCandidate:
        orng = OpeningRange(
            symbol=sym,
            session_date=DAY,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("100"),
            close=Decimal("100.5"),
            volume=1000,
            bar_open=datetime(DAY.year, DAY.month, DAY.day, 9, 15, tzinfo=IST),
        )
        return ScreenCandidate(
            symbol=sym,
            instrument_id=sym,
            direction="LONG",
            opening_range=orng,
            rvol5=Decimal(rvol),
            adv_value=Decimal("100000000"),
            prior_atr14=Decimal("5"),
            asset_class=asset,  # type: ignore[arg-type]
        )

    stocks, etfs = rank_candidates_split(
        [
            cand("AAA", "2.0", "STOCK"),
            cand("BBB", "3.0", "STOCK"),
            cand("NIFTYBEES", "2.5", "ETF"),
            cand("GOLDBEES", "4.0", "ETF"),
        ],
        DEFAULT_CONFIG_V1,
    )
    assert [r.candidate.symbol for r in stocks] == ["BBB", "AAA"]
    assert [r.rank for r in stocks] == [1, 2]
    assert [r.candidate.symbol for r in etfs] == ["GOLDBEES", "NIFTYBEES"]
    assert [r.rank for r in etfs] == [1, 2]


def test_morning_universe_includes_etfs():
    from app.domain.intraday.asset_class import classify_asset_class, morning_universe_symbols

    ordered, classes = morning_universe_symbols()
    assert len(ordered) > 400
    assert any(classes[s] == "ETF" for s in ordered)
    assert classify_asset_class("NIFTYBEES") == "ETF"
    assert classify_asset_class("RELIANCE") == "STOCK"


def test_board_phase_and_refresh():
    from app.application.intraday.morning_board_service import auto_refresh_seconds, resolve_board_phase

    day = DAY
    assert resolve_board_phase(datetime(day.year, day.month, day.day, 9, 0, tzinfo=IST), day) == "PRE_OPEN"
    assert auto_refresh_seconds("PRE_OPEN") == 60
    assert resolve_board_phase(datetime(day.year, day.month, day.day, 9, 17, tzinfo=IST), day) == "OR_BUILDING"
    assert resolve_board_phase(datetime(day.year, day.month, day.day, 9, 25, tzinfo=IST), day) == "LIVE_SCREEN"
    assert auto_refresh_seconds("LIVE_SCREEN") == 30


def test_breakout_long_fill_and_stop_bounds():
    orng = OpeningRange(
        symbol="AAA",
        session_date=DAY,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99.5"),
        close=Decimal("100.8"),
        volume=5000,
        bar_open=datetime(DAY.year, DAY.month, DAY.day, 9, 15, tzinfo=IST),
    )
    ranked_cand = ScreenCandidate(
        symbol="AAA",
        instrument_id="AAA",
        direction="LONG",
        opening_range=orng,
        rvol5=Decimal("2"),
        adv_value=Decimal("100000000"),
        prior_atr14=Decimal("7.5"),  # stop=0.75; OR range=1.5 → ratio 0.5 in [0.25,1.5]
        tick_size=Decimal("0.05"),
        spread=Decimal("0.05"),
    )
    from app.domain.intraday.types import RankedCandidate

    ranked = RankedCandidate(candidate=ranked_cand, rank=1)
    bars = [
        Candle(
            symbol="AAA",
            exchange="TEST",
            instrument_id=None,
            timeframe="1m",
            timestamp=datetime(DAY.year, DAY.month, DAY.day, 9, 21, tzinfo=IST),
            open=Decimal("101.0"),
            high=Decimal("101.4"),
            low=Decimal("100.9"),
            close=Decimal("101.3"),
            volume=1000,
        )
    ]
    hit = find_breakout_fill(ranked, bars, DAY)
    assert hit is not None
    entry, _ = hit
    assert entry >= orng.high

    err = validate_stop_bounds(
        entry=entry,
        stop_distance=Decimal("0.75"),
        opening_range=orng,
        spread=Decimal("0.05"),
        tick=Decimal("0.05"),
        config=DEFAULT_CONFIG_V1,
    )
    assert err is None


@pytest.mark.asyncio
async def test_demo_provider_1m_session_bars():
    provider = DemoMarketDataProvider()
    start = datetime(DAY.year, DAY.month, DAY.day, 9, 15, tzinfo=IST)
    end = datetime(DAY.year, DAY.month, DAY.day, 15, 29, tzinfo=IST)
    candles = await provider.get_candles("ORBDEMO", "1m", start, end)
    assert len(candles) > 300
    assert candles[0].timestamp.astimezone(IST).hour == 9
    assert candles[0].timestamp.astimezone(IST).minute == 15
    orng = build_opening_range("ORBDEMO", DAY, candles)
    assert orng is not None
    assert orng.volume > 0


@pytest.mark.asyncio
async def test_demo_session_runs_end_to_end():
    session_id, report = await run_demo_session(
        session_date=DAY,
        symbols=["ORBDEMO", "RELIANCE", "TCS"],
        equity=Decimal("1000000"),
    )
    assert session_id
    body = session_report_to_dict(report)
    assert body["strategy_id"] == "NSE_STOCKS_ETF_ORB_RVOL_5M_V1"
    assert body["config_hash"] == "CONFIG_V1"
    assert body["coverage_total"] == 3
    reasons = {r["symbol"]: r["reason"] for r in body["symbol_results"]}
    assert reasons
    assert any(r["reason"] == "TRADED" for r in body["symbol_results"])
    assert len(body["fills"]) >= 1
    assert len(body["closed_trades"]) >= 1
