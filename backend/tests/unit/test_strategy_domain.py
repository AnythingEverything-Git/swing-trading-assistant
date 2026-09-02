from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.strategy.strategy import StrategyEvidence, StrategyInput, StrategyResult, TradeCandidate
from app.domain.market_data import Candle


def make_candle(close_value: str, ts_index: int):
    return Candle(
        symbol="TST",
        exchange="TEST",
        instrument_id=1,
        timeframe="1d",
        timestamp=f"2020-01-{ts_index + 1:02d}T00:00:00Z",
        open=Decimal(close_value),
        high=Decimal(close_value),
        low=Decimal(close_value),
        close=Decimal(close_value),
        volume=1000,
    )


def _replace_candle(candle: Candle, **overrides):
    return replace(candle, **overrides)


def test_trade_candidate_valid_long():
    candidate = TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("110.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="breakout",
    )

    assert candidate.direction == "LONG"
    assert candidate.risk_per_share == Decimal("2.00")
    assert candidate.reward == Decimal("10.00")
    assert candidate.risk_reward_ratio == Decimal("5")


def test_trade_candidate_valid_short():
    candidate = TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="SHORT",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("102.00"),
        target=Decimal("90.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="retest",
    )

    assert candidate.direction == "SHORT"
    assert candidate.risk_per_share == Decimal("2.00")
    assert candidate.reward == Decimal("10.00")
    assert candidate.risk_reward_ratio == Decimal("5")


def test_strategy_result_with_candidate():
    candidate = TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("110.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="breakout",
    )
    evidence = StrategyEvidence(
        resistance=Decimal("101.50"),
        breakout_candle_index=19,
        breakout_candle_time=datetime(2024, 1, 20, tzinfo=timezone.utc),
        retest_candle_index=20,
        retest_candle_time=datetime(2024, 1, 21, tzinfo=timezone.utc),
        confirmation_candle_index=21,
        confirmation_candle_time=datetime(2024, 1, 22, tzinfo=timezone.utc),
        atr_value=Decimal("2.50"),
        volume_sma_value=Decimal("1200"),
        breakout_volume=2000,
        retest_low=Decimal("99.00"),
        confirmation_volume=2200,
        decision="valid breakout -> retest -> confirmation",
    )

    result = StrategyResult(has_setup=True, candidate=candidate, evidence=evidence)
    assert result.has_setup is True
    assert result.candidate == candidate
    assert result.evidence == evidence
    assert result.status == "VALID_SETUP"


def _make_valid_candidate():
    return TradeCandidate(
        symbol="TST",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("110.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="breakout",
    )


def _make_valid_evidence():
    return StrategyEvidence(
        resistance=Decimal("101.50"),
        breakout_candle_index=19,
        breakout_candle_time=datetime(2024, 1, 20, tzinfo=timezone.utc),
        retest_candle_index=20,
        retest_candle_time=datetime(2024, 1, 21, tzinfo=timezone.utc),
        confirmation_candle_index=21,
        confirmation_candle_time=datetime(2024, 1, 22, tzinfo=timezone.utc),
        atr_value=Decimal("2.50"),
        volume_sma_value=Decimal("1200"),
        breakout_volume=2000,
        retest_low=Decimal("99.00"),
        confirmation_volume=2200,
        decision="valid breakout -> retest -> confirmation",
    )


def test_strategy_result_requires_candidate_and_evidence_for_valid_setup():
    candidate = _make_valid_candidate()
    evidence = _make_valid_evidence()

    result = StrategyResult(has_setup=True, candidate=candidate, evidence=evidence)
    assert result.has_setup is True
    assert result.candidate == candidate
    assert result.evidence == evidence
    assert result.status == "VALID_SETUP"

    with pytest.raises(ValueError, match="candidate is required when has_setup is True"):
        StrategyResult(has_setup=True, candidate=None, evidence=evidence)

    with pytest.raises(ValueError, match="evidence is required when has_setup is True"):
        StrategyResult(has_setup=True, candidate=candidate, evidence=None)


def test_strategy_result_requires_candidate_and_evidence_to_be_absent_for_no_setup():
    candidate = _make_valid_candidate()
    evidence = _make_valid_evidence()

    result = StrategyResult(has_setup=False, candidate=None, evidence=None)
    assert result.has_setup is False
    assert result.candidate is None
    assert result.evidence is None
    assert result.status == "NO_SETUP"

    with pytest.raises(ValueError, match="candidate must be None when has_setup is False"):
        StrategyResult(has_setup=False, candidate=candidate, evidence=None)

    with pytest.raises(ValueError, match="evidence must be None when has_setup is False"):
        StrategyResult(has_setup=False, candidate=None, evidence=evidence)


def test_strategy_result_without_candidate():
    result = StrategyResult(has_setup=False, status="NO_SETUP", reason="insufficient data")
    assert result.has_setup is False
    assert result.candidate is None
    assert result.reason == "insufficient data"


def test_invalid_financial_values_rejected():
    with pytest.raises(ValueError):
        TradeCandidate(
            symbol="TST",
            timeframe="1d",
            direction="LONG",
            entry_price=Decimal("0"),
            stop_loss=Decimal("98.00"),
            target=Decimal("110.00"),
            risk_per_share=Decimal("0"),
            reward=Decimal("0"),
            risk_reward_ratio=Decimal("0"),
            setup_name="breakout",
        )

    with pytest.raises(ValueError):
        TradeCandidate(
            symbol="TST",
            timeframe="1d",
            direction="LONG",
            entry_price=Decimal("100.00"),
            stop_loss=Decimal("100.00"),
            target=Decimal("110.00"),
            risk_per_share=Decimal("0"),
            reward=Decimal("0"),
            risk_reward_ratio=Decimal("0"),
            setup_name="breakout",
        )

    with pytest.raises(ValueError):
        TradeCandidate(
            symbol="TST",
            timeframe="1d",
            direction="SHORT",
            entry_price=Decimal("100.00"),
            stop_loss=Decimal("98.00"),
            target=Decimal("110.00"),
            risk_per_share=Decimal("0"),
            reward=Decimal("0"),
            risk_reward_ratio=Decimal("0"),
            setup_name="breakout",
        )


def test_strategy_input_valid_and_ordered():
    candles = [
        make_candle("100", 0),
        make_candle("101", 1),
        make_candle("102", 2),
    ]
    strategy_input = StrategyInput(
        symbol="TST",
        timeframe="1d",
        candles=candles,
        indicator_values={"sma_10": Decimal("101.0")},
        metadata={"context": "test"},
    )

    assert strategy_input.symbol == "TST"
    assert strategy_input.candles[0].close == Decimal("100")
    assert strategy_input.indicator_values["sma_10"] == Decimal("101.0")


def test_strategy_input_rejects_unordered_candles():
    candles = [
        make_candle("102", 2),
        make_candle("101", 1),
    ]

    with pytest.raises(ValueError):
        StrategyInput(symbol="TST", timeframe="1d", candles=candles)


def _build_valid_setup_series():
    candles = []
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


def _as_of(candles, last_index):
    return candles[: last_index + 1]


def test_valid_swing_high_structure():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), open=Decimal("98"), high=Decimal("98.2"), low=Decimal("97.0"), close=Decimal("97.4"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc), open=Decimal("99.0"), high=Decimal("99.4"), low=Decimal("98.1"), close=Decimal("98.5"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc), open=Decimal("100.0"), high=Decimal("101.0"), low=Decimal("99.0"), close=Decimal("99.7"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 4, tzinfo=timezone.utc), open=Decimal("99.5"), high=Decimal("99.7"), low=Decimal("98.9"), close=Decimal("99.1"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 5, tzinfo=timezone.utc), open=Decimal("98.8"), high=Decimal("99.1"), low=Decimal("98.6"), close=Decimal("98.8"), volume=1000),
    ]

    assert strategy._is_confirmed_swing_high(candles, 2) is True


def test_valid_swing_low_structure():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), open=Decimal("102"), high=Decimal("103"), low=Decimal("101"), close=Decimal("101.5"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc), open=Decimal("101.5"), high=Decimal("102.0"), low=Decimal("100.5"), close=Decimal("101.0"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc), open=Decimal("100.8"), high=Decimal("101.3"), low=Decimal("99.4"), close=Decimal("99.9"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 4, tzinfo=timezone.utc), open=Decimal("100.4"), high=Decimal("101.2"), low=Decimal("100.0"), close=Decimal("100.6"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 5, tzinfo=timezone.utc), open=Decimal("100.7"), high=Decimal("101.5"), low=Decimal("100.2"), close=Decimal("100.8"), volume=1000),
    ]

    assert strategy._is_confirmed_swing_low(candles, 2) is True


def test_breakout_retest_confirmation_strategy_valid_setup():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))

    assert result.has_setup is True
    assert result.candidate is not None
    assert result.candidate.direction == "LONG"
    assert result.candidate.entry_price == Decimal("101.2")
    assert result.candidate.target == Decimal("106.9075209020929343441343422")
    assert result.candidate.risk_reward_ratio == Decimal("2")


def test_breakout_without_sufficient_volume_is_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[19] = _replace_candle(candles[19], volume=1200)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_breakout_without_retest_is_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[16] = _replace_candle(candles[16], low=Decimal("97.0"), close=Decimal("97.5"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_retest_after_breakout_occurs_within_window():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is True
    assert result.evidence is not None
    assert result.evidence.retest_candle_index == 20


def test_retest_before_breakout_is_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[20] = _replace_candle(candles[20], close=Decimal("99.0"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_retest_invalidation_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[16] = _replace_candle(candles[16], close=Decimal("98.5"), low=Decimal("98.0"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_retest_timeout_after_five_candles_expires():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    for idx in range(17, 22):
        candles[idx] = _replace_candle(candles[idx], close=Decimal("99.0"), low=Decimal("98.4"), high=Decimal("99.8"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_confirmation_before_retest_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[18] = _replace_candle(candles[18], close=Decimal("101.9"), high=Decimal("102.3"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_invalid_confirmation_volume_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[21] = _replace_candle(candles[21], volume=500)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_entry_equals_confirmation_close_and_sl_is_min_of_retest_low_and_resistance_minus_atr():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.candidate.entry_price == Decimal("101.2")
    assert result.candidate.stop_loss == Decimal("98.34623954895353282793282890")


def test_stop_distance_filter_rejects_large_stop():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[21] = _replace_candle(candles[21], close=Decimal("106.0"), low=Decimal("96.5"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_target_rr_and_risk_validation():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.candidate.risk_per_share == Decimal("2.85376045104646717206717110")
    assert result.candidate.target == Decimal("106.9075209020929343441343422")
    assert result.candidate.reward == Decimal("5.7075209020929343441343422")
    assert result.candidate.risk_reward_ratio == Decimal("2")


def test_invalid_non_positive_risk_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    candles[21] = _replace_candle(candles[21], close=Decimal("99.0"))
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_insufficient_historical_candles_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), open=Decimal("101"), high=Decimal("101"), low=Decimal("100"), close=Decimal("100.5"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc), open=Decimal("100.5"), high=Decimal("101.2"), low=Decimal("100.2"), close=Decimal("101"), volume=1000),
    ]
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    assert result.has_setup is False


def test_strategy_is_deterministic_and_has_no_look_ahead_bias():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    first = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))
    second = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=list(candles)))
    assert first == second
    assert first.has_setup is True


def test_no_look_ahead_bias_for_swing_high_detection():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    candles = _build_valid_setup_series()
    assert strategy._is_confirmed_swing_high(candles, 5) is True
    assert strategy._is_confirmed_swing_high(candles, 15) is False


def test_resistance_selection_excludes_swing_high_one_candle_before_breakout():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), open=Decimal("98.0"), high=Decimal("99.0"), low=Decimal("97.0"), close=Decimal("98.5"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc), open=Decimal("99.0"), high=Decimal("100.4"), low=Decimal("98.6"), close=Decimal("99.2"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc), open=Decimal("99.2"), high=Decimal("99.8"), low=Decimal("98.5"), close=Decimal("99.1"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 4, tzinfo=timezone.utc), open=Decimal("100.0"), high=Decimal("101.8"), low=Decimal("99.4"), close=Decimal("100.7"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 5, tzinfo=timezone.utc), open=Decimal("100.8"), high=Decimal("100.5"), low=Decimal("99.2"), close=Decimal("99.8"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 6, tzinfo=timezone.utc), open=Decimal("100.0"), high=Decimal("100.9"), low=Decimal("99.5"), close=Decimal("100.6"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 7, tzinfo=timezone.utc), open=Decimal("100.4"), high=Decimal("99.6"), low=Decimal("98.7"), close=Decimal("99.2"), volume=1000),
    ]
    breakout_index = 5
    assert strategy._is_confirmed_swing_high(candles, breakout_index - 2) is True
    assert strategy._is_confirmed_swing_high(candles, breakout_index - 1) is False

    eligible = [idx for idx in range(2, breakout_index - 1) if strategy._is_confirmed_swing_high(candles, idx)]
    assert eligible == [3]


def test_resistance_selection_allows_swing_high_two_candles_before_breakout():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    candles = [
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), open=Decimal("98.0"), high=Decimal("99.0"), low=Decimal("97.0"), close=Decimal("98.5"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc), open=Decimal("99.0"), high=Decimal("100.4"), low=Decimal("98.6"), close=Decimal("99.2"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc), open=Decimal("99.2"), high=Decimal("99.8"), low=Decimal("98.5"), close=Decimal("99.1"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 4, tzinfo=timezone.utc), open=Decimal("100.0"), high=Decimal("101.8"), low=Decimal("99.4"), close=Decimal("100.7"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 5, tzinfo=timezone.utc), open=Decimal("100.8"), high=Decimal("100.5"), low=Decimal("99.2"), close=Decimal("99.8"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 6, tzinfo=timezone.utc), open=Decimal("100.0"), high=Decimal("100.9"), low=Decimal("99.5"), close=Decimal("100.6"), volume=1000),
        Candle(symbol="TST", exchange="TEST", instrument_id=1, timeframe="1d", timestamp=datetime(2024, 1, 7, tzinfo=timezone.utc), open=Decimal("100.4"), high=Decimal("99.6"), low=Decimal("98.7"), close=Decimal("99.2"), volume=1000),
    ]
    breakout_index = 5
    assert strategy._is_confirmed_swing_high(candles, breakout_index - 2) is True
    assert strategy._is_confirmed_swing_high(candles, breakout_index - 1) is False
    assert strategy._is_confirmed_swing_high(candles, breakout_index - 3) is False


def test_confirmation_window_allows_exactly_one_two_and_three_candles_after_retest():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    base = _build_valid_setup_series()
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
                high=Decimal("100.2"),
                low=Decimal("99.0"),
                close=Decimal("99.4"),
                volume=500,
            )

        candles[confirmation_index] = _replace_candle(
            candles[confirmation_index],
            open=Decimal("100.8"),
            high=Decimal("101.8"),
            low=Decimal("100.2"),
            close=Decimal("101.2"),
            volume=2200,
        )

        result = strategy.evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(candles, confirmation_index)))
        assert result.has_setup is True


def test_confirmation_on_fourth_candle_after_retest_is_rejected():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    strategy = BreakoutRetestConfirmationStrategy()
    candles = _build_valid_setup_series()
    retest_index = 20
    confirmation_index = retest_index + 4

    for idx in range(retest_index + 1, min(len(candles), confirmation_index + 1)):
        if idx == confirmation_index:
            continue
        candles[idx] = _replace_candle(
            candles[idx],
            open=Decimal("100.0"),
            high=Decimal("100.2"),
            low=Decimal("99.0"),
            close=Decimal("99.4"),
            volume=500,
        )

    candles[confirmation_index] = _replace_candle(
        candles[confirmation_index],
        open=Decimal("100.8"),
        high=Decimal("101.8"),
        low=Decimal("100.2"),
        close=Decimal("101.2"),
        volume=2200,
    )

    result = strategy.evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(candles, confirmation_index)))
    assert result.has_setup is False


def test_strategy_evidence_valid_construction_and_immutability():
    from dataclasses import FrozenInstanceError

    from app.domain.strategy.strategy import StrategyEvidence

    evidence = StrategyEvidence(
        resistance=Decimal("101.50"),
        breakout_candle_index=19,
        breakout_candle_time=datetime(2024, 1, 20, tzinfo=timezone.utc),
        retest_candle_index=20,
        retest_candle_time=datetime(2024, 1, 21, tzinfo=timezone.utc),
        confirmation_candle_index=21,
        confirmation_candle_time=datetime(2024, 1, 22, tzinfo=timezone.utc),
        atr_value=Decimal("2.50"),
        volume_sma_value=Decimal("1200"),
        breakout_volume=2000,
        retest_low=Decimal("99.00"),
        confirmation_volume=2200,
        decision="valid breakout -> retest -> confirmation",
    )

    assert evidence.resistance == Decimal("101.50")
    assert isinstance(evidence.atr_value, Decimal)
    assert isinstance(evidence.volume_sma_value, Decimal)
    assert isinstance(evidence.retest_low, Decimal)
    with pytest.raises(FrozenInstanceError):
        evidence.decision = "changed"


def test_strategy_evidence_rejects_invalid_required_values():
    from app.domain.strategy.strategy import StrategyEvidence

    base_kwargs = {
        "resistance": Decimal("101.50"),
        "breakout_candle_index": 19,
        "breakout_candle_time": datetime(2024, 1, 20, tzinfo=timezone.utc),
        "retest_candle_index": 20,
        "retest_candle_time": datetime(2024, 1, 21, tzinfo=timezone.utc),
        "confirmation_candle_index": 21,
        "confirmation_candle_time": datetime(2024, 1, 22, tzinfo=timezone.utc),
        "atr_value": Decimal("2.50"),
        "volume_sma_value": Decimal("1200"),
        "breakout_volume": 2000,
        "retest_low": Decimal("99.00"),
        "confirmation_volume": 2200,
    }

    with pytest.raises(ValueError):
        StrategyEvidence(decision="", **base_kwargs)
    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "resistance": Decimal("0"), "decision": "ok"})
    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "atr_value": Decimal("-1"), "decision": "ok"})
    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "volume_sma_value": Decimal("0"), "decision": "ok"})


def test_strategy_evidence_rejects_negative_indexes_and_invalid_volumes():
    from app.domain.strategy.strategy import StrategyEvidence

    base_kwargs = {
        "resistance": Decimal("101.50"),
        "breakout_candle_index": 19,
        "breakout_candle_time": datetime(2024, 1, 20, tzinfo=timezone.utc),
        "retest_candle_index": 20,
        "retest_candle_time": datetime(2024, 1, 21, tzinfo=timezone.utc),
        "confirmation_candle_index": 21,
        "confirmation_candle_time": datetime(2024, 1, 22, tzinfo=timezone.utc),
        "atr_value": Decimal("2.50"),
        "volume_sma_value": Decimal("1200"),
        "breakout_volume": 2000,
        "retest_low": Decimal("99.00"),
        "confirmation_volume": 2200,
        "decision": "ok",
    }

    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "breakout_candle_index": -1})
    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "retest_candle_index": -5})
    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "confirmation_volume": -1})
    with pytest.raises(ValueError):
        StrategyEvidence(**{**base_kwargs, "breakout_volume": -10})


def test_strategy_result_evidence_is_declared_and_immutable():
    from dataclasses import FrozenInstanceError

    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))

    assert result.has_setup is True
    assert result.evidence is not None
    assert result.evidence.breakout_candle_index == 19
    assert result.evidence.retest_candle_index == 20
    assert result.evidence.confirmation_candle_index == 21
    assert not hasattr(result.candidate, "resistance")
    with pytest.raises(FrozenInstanceError):
        result.evidence.breakout_candle_index = 99


def test_valid_setup_confirmed_on_final_candle_returns_setup():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _as_of(_build_valid_setup_series(), 21)
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))

    assert result.has_setup is True
    assert result.status == "VALID_SETUP"
    assert result.evidence is not None
    assert result.evidence.confirmation_candle_index == len(candles) - 1
    assert result.candidate is not None
    assert result.candidate.direction == "LONG"


def test_valid_setup_followed_by_extra_candles_returns_no_setup():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    candles = _build_valid_setup_series()
    result = BreakoutRetestConfirmationStrategy().evaluate(StrategyInput(symbol="TST", timeframe="1d", candles=candles))

    assert len(candles) > 22
    assert result.has_setup is False
    assert result.status == "NO_SETUP"
    assert result.candidate is None
    assert result.evidence is None


def test_earlier_valid_setup_is_not_returned_without_current_confirmation():
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy

    series = _build_valid_setup_series()
    confirmed = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(series, 21))
    )
    later = BreakoutRetestConfirmationStrategy().evaluate(
        StrategyInput(symbol="TST", timeframe="1d", candles=_as_of(series, 22))
    )

    assert confirmed.has_setup is True
    assert confirmed.evidence.confirmation_candle_index == 21
    assert later.has_setup is False
    assert later.candidate is None
    assert later.evidence is None
