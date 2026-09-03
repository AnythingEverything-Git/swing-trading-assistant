"""Focused unit tests for OpportunityScanService orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.scan.opportunity_scan_service import OpportunityScanService
from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
from app.domain.strategy.strategy import (
    BreakoutRetestConfirmationStrategy,
    StrategyEvidence,
    StrategyResult,
    TradeCandidate,
)
from app.infrastructure.market_data.deterministic_setup_series import (
    build_two_independent_setup_series,
)
from app.infrastructure.market_data.mock_provider import MockMarketDataProvider


def _evidence() -> StrategyEvidence:
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


def _candidate(symbol: str = "AAA") -> TradeCandidate:
    return TradeCandidate(
        symbol=symbol,
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("98.00"),
        target=Decimal("104.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="BreakoutRetestConfirmation",
    )


def _setup_result(symbol: str) -> StrategyResult:
    return StrategyResult(
        has_setup=True,
        candidate=_candidate(symbol),
        evidence=_evidence(),
        status="VALID_SETUP",
    )


def _no_setup_result() -> StrategyResult:
    return StrategyResult(has_setup=False, status="NO_SETUP", reason="stubbed")


class FakeEvaluationService:
    """Predetermined per-symbol results; records evaluate calls."""

    def __init__(self, results_by_symbol: dict[str, StrategyResult]) -> None:
        self.results_by_symbol = results_by_symbol
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> StrategyResult:
        self.calls.append((symbol, timeframe, start, end))
        return self.results_by_symbol[symbol]


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 2, 12, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_empty_symbol_list_scans_zero():
    evaluation = FakeEvaluationService({})
    result = await OpportunityScanService(evaluation).scan([], "1d", START, END)

    assert result.symbols_scanned == 0
    assert result.eligible_count == 0
    assert result.opportunities == ()
    assert evaluation.calls == []


@pytest.mark.asyncio
async def test_one_symbol_with_setup_returns_existing_candidate_and_evidence():
    setup = _setup_result("AAA")
    evaluation = FakeEvaluationService({"AAA": setup})

    result = await OpportunityScanService(evaluation).scan(["AAA"], "1d", START, END)

    assert result.symbols_scanned == 1
    assert result.eligible_count == 1
    assert len(result.opportunities) == 1
    opportunity = result.opportunities[0]
    assert opportunity.symbol == "AAA"
    assert opportunity.candidate is setup.candidate
    assert opportunity.evidence is setup.evidence
    assert opportunity.candidate.direction == "LONG"
    assert opportunity.candidate.entry_price == Decimal("100.00")
    assert opportunity.candidate.stop_loss == Decimal("98.00")
    assert opportunity.candidate.target == Decimal("104.00")
    assert opportunity.candidate.risk_reward_ratio == Decimal("2")
    assert opportunity.evidence.decision == "valid breakout -> retest -> confirmation"
    assert evaluation.calls == [("AAA", "1d", START, END)]


@pytest.mark.asyncio
async def test_one_symbol_with_no_setup_is_scanned_but_not_eligible():
    evaluation = FakeEvaluationService({"BBB": _no_setup_result()})

    result = await OpportunityScanService(evaluation).scan(["BBB"], "1d", START, END)

    assert result.symbols_scanned == 1
    assert result.eligible_count == 0
    assert result.opportunities == ()


@pytest.mark.asyncio
async def test_mixed_symbols_return_only_eligible_in_input_order():
    evaluation = FakeEvaluationService(
        {
            "AAA": _no_setup_result(),
            "BBB": _setup_result("BBB"),
            "CCC": _no_setup_result(),
            "DDD": _setup_result("DDD"),
        }
    )

    result = await OpportunityScanService(evaluation).scan(
        ["AAA", "BBB", "CCC", "DDD"],
        "1d",
        START,
        END,
    )

    assert result.symbols_scanned == 4
    assert result.eligible_count == 2
    assert [item.symbol for item in result.opportunities] == ["BBB", "DDD"]
    assert [call[0] for call in evaluation.calls] == ["AAA", "BBB", "CCC", "DDD"]
    assert len(evaluation.calls) == 4


@pytest.mark.asyncio
async def test_confirmation_not_on_last_bar_remains_ineligible_via_real_strategy():
    """Preserve NOW semantics through StrategyEvaluationService + real strategy."""
    series = build_two_independent_setup_series()
    assert len(series) > 42  # confirmation at 41 is not the final candle
    provider = MockMarketDataProvider(candles=series)
    evaluation = StrategyEvaluationService(provider, BreakoutRetestConfirmationStrategy())
    assert type(evaluation.strategy) is BreakoutRetestConfirmationStrategy

    # Truncated to confirmation bar → eligible NOW
    confirmed_end = series[41].timestamp
    confirmed = await OpportunityScanService(evaluation).scan(
        ["TST"],
        "1d",
        series[0].timestamp,
        confirmed_end,
    )
    assert confirmed.symbols_scanned == 1
    assert confirmed.eligible_count == 1
    assert confirmed.opportunities[0].candidate.entry_price == Decimal("108.0")
    assert confirmed.opportunities[0].evidence.confirmation_candle_index == 41

    # Full series includes a bar after confirmation → not eligible NOW
    later = await OpportunityScanService(evaluation).scan(
        ["TST"],
        "1d",
        series[0].timestamp,
        series[-1].timestamp,
    )
    assert later.symbols_scanned == 1
    assert later.eligible_count == 0
    assert later.opportunities == ()
