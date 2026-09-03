"""Focused unit tests for UniverseScanReportService outcome classification."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.scan.universe_scan_report_service import UniverseScanReportService
from app.domain.strategy.strategy import StrategyEvidence, StrategyResult, TradeCandidate
from app.domain.universe import UniverseSnapshot


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 2, 12, tzinfo=timezone.utc)


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


def _candidate(symbol: str) -> TradeCandidate:
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


class FakeEvaluation:
    def __init__(self, behavior: dict[str, object]) -> None:
        self.behavior = behavior
        self.calls: list[str] = []

    async def evaluate(self, symbol: str, timeframe: str, start, end):
        self.calls.append(symbol)
        action = self.behavior[symbol]
        if isinstance(action, Exception):
            raise action
        return action


class FakeUniverse:
    def __init__(self, symbols: tuple[str, ...]) -> None:
        self._snapshot = UniverseSnapshot(
            name="TEST",
            version="v1",
            as_of=None,
            symbols=symbols,
        )

    def get_snapshot(self) -> UniverseSnapshot:
        return self._snapshot


@pytest.mark.asyncio
async def test_report_classifies_eligible_no_setup_unavailable_and_error():
    evaluation = FakeEvaluation(
        {
            "AAA": StrategyResult(
                has_setup=True,
                candidate=_candidate("AAA"),
                evidence=_evidence(),
                status="VALID_SETUP",
            ),
            "BBB": StrategyResult(has_setup=False, status="NO_SETUP", reason="none"),
            "CCC": ValueError("candles must contain at least one value"),
            "DDD": RuntimeError("db unavailable"),
        }
    )
    report = await UniverseScanReportService(evaluation).scan(
        ["AAA", "BBB", "CCC", "DDD"],
        "1d",
        START,
        END,
    )

    assert report.symbols_scanned == 4
    assert report.eligible_count == 1
    assert report.no_setup_count == 1
    assert report.unavailable_count == 1
    assert report.error_count == 1
    assert [opp.symbol for opp in report.opportunities] == ["AAA"]
    assert [(item.symbol, item.status) for item in report.issues] == [
        ("CCC", "UNAVAILABLE"),
        ("DDD", "ERROR"),
    ]
    # Does not stop after unavailable/error
    assert evaluation.calls == ["AAA", "BBB", "CCC", "DDD"]


@pytest.mark.asyncio
async def test_report_scan_universe_uses_snapshot_symbols():
    evaluation = FakeEvaluation(
        {
            "AAA": StrategyResult(has_setup=False, status="NO_SETUP"),
            "BBB": StrategyResult(has_setup=False, status="NO_SETUP"),
        }
    )
    report = await UniverseScanReportService(evaluation).scan_universe(
        FakeUniverse(("AAA", "BBB")),
        "1d",
        START,
        END,
    )
    assert report.symbols_scanned == 2
    assert report.no_setup_count == 2
    assert report.eligible_count == 0
    assert report.unavailable_count == 0
    assert report.error_count == 0
    assert report.issues == ()


@pytest.mark.asyncio
async def test_issue_list_is_capped():
    behavior = {
        f"S{i}": ValueError("candles must contain at least one value") for i in range(5)
    }
    evaluation = FakeEvaluation(behavior)
    report = await UniverseScanReportService(evaluation, issue_limit=2).scan(
        tuple(behavior.keys()),
        "1d",
        START,
        END,
    )
    assert report.unavailable_count == 5
    assert len(report.issues) == 2
