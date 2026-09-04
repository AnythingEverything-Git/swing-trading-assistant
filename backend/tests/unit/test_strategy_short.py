"""Exhaustive SHORT (breakdown → retest → confirmation) strategy tests.

SHORT series is a geometric reflection of the validated LONG fixture so every
LONG threshold maps 1:1 onto its SHORT mirror.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.market_data import Candle
from app.domain.strategy.strategy import (
    BreakoutRetestConfirmationStrategy,
    FormingSetup,
    StrategyEvidence,
    StrategyInput,
    StrategyResult,
    TradeCandidate,
)


def _replace_candle(candle: Candle, **overrides):
    return replace(candle, **overrides)


def _build_valid_long_setup_series():
    levels = [
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
        (102.5, 102.8, 101.5, 102.0, 2300),
        (101.8, 102.0, 100.9, 101.5, 2100),
        (102.0, 102.4, 101.3, 101.7, 2200),
    ]
    candles = []
    for idx, (open_, high, low, close, volume) in enumerate(levels):
        candles.append(
            Candle(
                symbol="TST",
                exchange="TEST",
                instrument_id=1,
                timeframe="1d",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=idx),
                open=Decimal(str(open_)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=volume,
            )
        )
    return candles


def _invert_series(candles: list[Candle], pivot: Decimal = Decimal("100")) -> list[Candle]:
    """Reflect OHLC around pivot so a LONG setup becomes a SHORT setup."""
    inverted = []
    for candle in candles:
        inverted.append(
            replace(
                candle,
                open=pivot * 2 - candle.open,
                close=pivot * 2 - candle.close,
                high=pivot * 2 - candle.low,
                low=pivot * 2 - candle.high,
            )
        )
    return inverted


def _build_valid_short_setup_series():
    return _invert_series(_build_valid_long_setup_series())


def _as_of(candles, last_index):
    return candles[: last_index + 1]


def test_short_valid_breakdown_retest_confirmation():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )

    assert result.has_setup is True
    assert result.candidate is not None
    assert result.evidence is not None
    assert result.candidate.direction == "SHORT"
    assert result.evidence.direction == "SHORT"
    assert result.candidate.setup_name == "BreakdownRetestConfirmation"
    assert result.candidate.entry_price == Decimal("98.8")
    assert result.candidate.stop_loss > result.candidate.entry_price
    assert result.candidate.target < result.candidate.entry_price
    assert result.candidate.risk_reward_ratio == Decimal("2")
    assert result.evidence.confirmation_candle_index == len(candles) - 1
    assert result.evidence.decision == "valid breakdown -> retest -> confirmation"


def test_short_entry_sl_target_mirror_long_geometry():
    long_candles = _as_of(_build_valid_long_setup_series(), 21)
    short_candles = _as_of(_build_valid_short_setup_series(), 21)
    long_result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=long_candles)
    )
    short_result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=short_candles)
    )
    pivot = Decimal("100")
    assert long_result.has_setup and short_result.has_setup
    assert short_result.candidate.entry_price == pivot * 2 - long_result.candidate.entry_price
    assert short_result.candidate.stop_loss == pivot * 2 - long_result.candidate.stop_loss
    assert short_result.candidate.target == pivot * 2 - long_result.candidate.target
    assert short_result.candidate.risk_per_share == long_result.candidate.risk_per_share


def test_short_breakdown_without_sufficient_volume_rejected():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    candles[19] = _replace_candle(candles[19], volume=1200)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_breakdown_without_retest_rejected():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    baseline = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=list(candles))
    )
    assert baseline.has_setup is True
    support = baseline.evidence.structure_level
    # After breakdown, stay deep below support and never tag it for a retest.
    for idx in range(20, 22):
        candles[idx] = _replace_candle(
            candles[idx],
            open=support - Decimal("2"),
            high=support - Decimal("1.5"),
            low=support - Decimal("3"),
            close=support - Decimal("2"),
            volume=1500,
        )
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_retest_after_breakdown_within_window():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is True
    assert result.evidence.retest_candle_index == 20


def test_short_retest_invalidation_when_close_reclaims_above_support():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    baseline = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=list(candles))
    )
    assert baseline.has_setup is True
    support = baseline.evidence.structure_level
    # Immediate reclaim above support + buffer invalidates the breakdown sequence.
    candles[20] = _replace_candle(
        candles[20],
        open=support + Decimal("0.5"),
        high=support + Decimal("2"),
        low=support - Decimal("0.2"),
        close=support + Decimal("1.5"),
        volume=1500,
    )
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_retest_timeout_after_five_candles():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    for idx in range(17, 22):
        candles[idx] = _replace_candle(
            candles[idx],
            close=Decimal("101.0"),
            high=Decimal("101.6"),
            low=Decimal("100.2"),
        )
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_invalid_confirmation_volume_rejected():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    candles[21] = _replace_candle(candles[21], volume=500)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_stop_distance_filter_rejects_large_stop():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    candles[21] = _replace_candle(candles[21], close=Decimal("94.0"), high=Decimal("103.5"))
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_confirmation_must_be_on_final_candle():
    candles = _build_valid_short_setup_series()
    confirmed = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(candles, 21))
    )
    later = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(candles, 22))
    )
    assert confirmed.has_setup is True
    assert later.has_setup is False


def test_short_confirmation_window_allows_one_two_three_bars():
    strategy = BreakoutRetestConfirmationStrategy()
    base = _build_valid_short_setup_series()
    for offset in (1, 2, 3):
        candles = [c for c in base]
        retest_index = 20
        confirmation_index = retest_index + offset
        for idx in range(retest_index + 1, min(len(candles), confirmation_index + 1)):
            if idx == confirmation_index:
                continue
            candles[idx] = _replace_candle(
                candles[idx],
                open=Decimal("100.0"),
                high=Decimal("101.0"),
                low=Decimal("99.8"),
                close=Decimal("100.6"),
                volume=500,
            )
        candles[confirmation_index] = _replace_candle(
            candles[confirmation_index],
            open=Decimal("99.2"),
            high=Decimal("99.8"),
            low=Decimal("98.2"),
            close=Decimal("98.8"),
            volume=2200,
        )
        result = strategy.evaluate(
            StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(candles, confirmation_index))
        )
        assert result.has_setup is True
        assert result.candidate.direction == "SHORT"


def test_short_confirmation_on_fourth_bar_rejected():
    strategy = BreakoutRetestConfirmationStrategy()
    candles = _build_valid_short_setup_series()
    retest_index = 20
    confirmation_index = retest_index + 4
    for idx in range(retest_index + 1, min(len(candles), confirmation_index + 1)):
        if idx == confirmation_index:
            continue
        candles[idx] = _replace_candle(
            candles[idx],
            open=Decimal("100.0"),
            high=Decimal("101.0"),
            low=Decimal("99.8"),
            close=Decimal("100.6"),
            volume=500,
        )
    candles[confirmation_index] = _replace_candle(
        candles[confirmation_index],
        open=Decimal("99.2"),
        high=Decimal("99.8"),
        low=Decimal("98.2"),
        close=Decimal("98.8"),
        volume=2200,
    )
    result = strategy.evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(candles, confirmation_index))
    )
    assert result.has_setup is False


def test_short_sl_is_max_of_retest_high_and_support_plus_atr():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is True
    support = result.evidence.structure_level
    retest_high = result.evidence.retest_extreme
    # Stop must sit at or above both structural references.
    assert result.candidate.stop_loss >= support
    assert result.candidate.stop_loss >= retest_high


def test_short_forming_awaiting_retest():
    candles = _as_of(_build_valid_short_setup_series(), 19)
    forming = BreakoutRetestConfirmationStrategy().inspect_forming(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert forming is not None
    assert forming.direction == "SHORT"
    assert forming.stage == "AWAITING_RETEST"
    assert forming.retest_candle_index is None


def test_short_forming_awaiting_confirmation():
    candles = _as_of(_build_valid_short_setup_series(), 20)
    forming = BreakoutRetestConfirmationStrategy().inspect_forming(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert forming is not None
    assert forming.direction == "SHORT"
    assert forming.stage == "AWAITING_CONFIRMATION"
    assert forming.retest_candle_index == 20


def test_short_forming_none_when_confirmed_now():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    strategy = BreakoutRetestConfirmationStrategy()
    assert strategy.evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles)).has_setup
    assert strategy.inspect_forming(StrategyInput(symbol="TST", timeframe="1d", candles=candles)) is None


def test_short_deterministic():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    first = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    second = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=list(candles))
    )
    assert first == second


def test_long_still_preferred_when_only_long_exists():
    candles = _as_of(_build_valid_long_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is True
    assert result.candidate.direction == "LONG"


def test_short_evidence_properties():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.evidence.support == result.evidence.resistance
    assert result.evidence.retest_high == result.evidence.retest_low
    with pytest.raises(AttributeError):
        _ = StrategyEvidence(
            resistance=Decimal("100"),
            breakout_candle_index=1,
            breakout_candle_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            retest_candle_index=2,
            retest_candle_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            confirmation_candle_index=3,
            confirmation_candle_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
            atr_value=Decimal("1"),
            volume_sma_value=Decimal("1000"),
            breakout_volume=2000,
            retest_low=Decimal("99"),
            confirmation_volume=2000,
            decision="long",
            direction="LONG",
        ).support


def test_strategy_result_rejects_direction_mismatch():
    candidate = TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="SHORT",
        entry_price=Decimal("100"),
        stop_loss=Decimal("102"),
        target=Decimal("96"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="BreakdownRetestConfirmation",
    )
    evidence = StrategyEvidence(
        resistance=Decimal("101"),
        breakout_candle_index=1,
        breakout_candle_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        retest_candle_index=2,
        retest_candle_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        confirmation_candle_index=3,
        confirmation_candle_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        atr_value=Decimal("1"),
        volume_sma_value=Decimal("1000"),
        breakout_volume=2000,
        retest_low=Decimal("101.5"),
        confirmation_volume=2000,
        decision="valid breakdown -> retest -> confirmation",
        direction="LONG",
    )
    with pytest.raises(ValueError, match="candidate.direction must match evidence.direction"):
        StrategyResult(has_setup=True, candidate=candidate, evidence=evidence)


def test_forming_setup_requires_direction():
    with pytest.raises(ValueError):
        FormingSetup(
            symbol="TST",
            timeframe="1d",
            stage="AWAITING_RETEST",
            resistance=Decimal("100"),
            breakout_candle_index=10,
            breakout_candle_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            breakout_volume=2000,
            atr_value=Decimal("1"),
            volume_sma_value=Decimal("1000"),
            bars_elapsed=0,
            bars_remaining=5,
            reason="x",
            direction="SIDEWAYS",  # type: ignore[arg-type]
        )


def test_short_confirmation_requires_close_below_prior_low_and_support():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    # Weaken confirmation so it fails prior-low break.
    candles[21] = _replace_candle(
        candles[21],
        close=Decimal("99.5"),
        low=Decimal("99.0"),
        high=Decimal("100.0"),
        volume=2200,
    )
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False


def test_short_non_positive_risk_rejected():
    candles = _as_of(_build_valid_short_setup_series(), 21)
    candles[21] = _replace_candle(candles[21], close=Decimal("101.0"))
    result = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)
    )
    assert result.has_setup is False
