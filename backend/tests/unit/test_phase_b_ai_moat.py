"""Phase B AI moat unit tests: guardrails, critic rank neutrality, book solver, similar outcomes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.narrative.grounded_narrator import validate_grounded_text
from app.application.narrative.quality_critic import critique_opportunity
from app.application.research.similar_setups import (
    SetupFingerprint,
    fingerprint_distance,
    forward_outcome_from_candles,
    rank_similar,
)
from app.application.scan.book_constructor import build_personal_book
from app.application.scan.opportunity_scan_service import EligibleOpportunity
from app.application.scan.quality_score import QualityScore, score_opportunity
from app.application.scan.scan_presentation import PresentedOpportunity, present_scan
from app.domain.market_data import Candle
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate


def _candidate(symbol: str = "TCS", direction: str = "LONG") -> TradeCandidate:
    if direction == "SHORT":
        return TradeCandidate(
            symbol=symbol,
            timeframe="1d",
            direction="SHORT",
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            target=Decimal("90"),
            risk_per_share=Decimal("5"),
            reward=Decimal("10"),
            risk_reward_ratio=Decimal("2"),
            setup_name="breakout_retest",
        )
    return TradeCandidate(
        symbol=symbol,
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        risk_per_share=Decimal("5"),
        reward=Decimal("10"),
        risk_reward_ratio=Decimal("2"),
        setup_name="breakout_retest",
    )


def _evidence(direction: str = "LONG") -> StrategyEvidence:
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    return StrategyEvidence(
        resistance=Decimal("99"),
        breakout_candle_index=10,
        breakout_candle_time=now - timedelta(days=5),
        retest_candle_index=12,
        retest_candle_time=now - timedelta(days=3),
        confirmation_candle_index=14,
        confirmation_candle_time=now,
        atr_value=Decimal("2"),
        volume_sma_value=Decimal("1000"),
        breakout_volume=3000,
        retest_low=Decimal("98"),
        confirmation_volume=2000,
        decision="confirmed",
        direction=direction,  # type: ignore[arg-type]
    )


def test_guardrail_rejects_invented_prices():
    facts = {"entry": "100.00", "stop": "95.00", "target": "110.00", "source_text": "Entry 100.00"}
    assert validate_grounded_text("Entry is 100.00 near stop 95.00", facts) is not None
    assert validate_grounded_text("Buy at 999.99 instead", facts) is None


@pytest.mark.asyncio
async def test_critic_does_not_change_rank_order():
    from app.application.scan.universe_scan_report_service import UniverseScanReport

    high = EligibleOpportunity(symbol="AAA", candidate=_candidate("AAA"), evidence=_evidence())
    low = EligibleOpportunity(
        symbol="BBB",
        candidate=_candidate("BBB"),
        evidence=StrategyEvidence(
            resistance=Decimal("99"),
            breakout_candle_index=10,
            breakout_candle_time=datetime(2026, 1, 10, tzinfo=timezone.utc),
            retest_candle_index=12,
            retest_candle_time=datetime(2026, 1, 12, tzinfo=timezone.utc),
            confirmation_candle_index=14,
            confirmation_candle_time=datetime(2026, 1, 15, tzinfo=timezone.utc),
            atr_value=Decimal("2"),
            volume_sma_value=Decimal("1000"),
            breakout_volume=1200,
            retest_low=Decimal("90"),
            confirmation_volume=1100,
            decision="confirmed",
            direction="LONG",
        ),
    )
    report = UniverseScanReport(
        symbols_scanned=2,
        eligible_count=2,
        no_setup_count=0,
        unavailable_count=0,
        error_count=0,
        opportunities=(high, low),
        issues=(),
    )
    presented = present_scan(report, top_n=2)
    before = [item.opportunity.symbol for item in presented.opportunities]
    for item in presented.opportunities:
        await critique_opportunity(
            None,
            candidate=item.opportunity.candidate,
            evidence=item.opportunity.evidence,
            quality=item.quality,
        )
    after = [item.opportunity.symbol for item in presented.opportunities]
    assert before == after
    assert before[0] == "AAA"


def test_book_solver_is_deterministic():
    items = []
    for idx, symbol in enumerate(["AAA", "BBB", "CCC", "DDD"], start=1):
        cand = _candidate(symbol)
        evid = _evidence()
        quality = score_opportunity(cand, evid)
        items.append(
            PresentedOpportunity(
                opportunity=EligibleOpportunity(symbol=symbol, candidate=cand, evidence=evid),
                quality=quality,
                rank=idx,
                narrative="n",
                invalidation="i",
                quantity=None,
                risk_amount=None,
            )
        )
    book1 = build_personal_book(
        items,
        account_equity=Decimal("200000"),
        risk_percent=Decimal("1"),
        max_positions=3,
        open_symbols={"CCC"},
    )
    book2 = build_personal_book(
        items,
        account_equity=Decimal("200000"),
        risk_percent=Decimal("1"),
        max_positions=3,
        open_symbols={"CCC"},
    )
    assert [p.symbol for p in book1.picks] == [p.symbol for p in book2.picks]
    assert "CCC" not in {p.symbol for p in book1.picks}
    assert len(book1.picks) == 3


def test_similar_outcomes_from_candles_only():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(
            symbol="TCS",
            exchange="NSE",
            instrument_id=None,
            timeframe="1d",
            timestamp=start + timedelta(days=i),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal(str(100 + i)),
            volume=1000,
        )
        for i in range(15)
    ]
    conf = start + timedelta(days=2)
    ret, hit_t, hit_s = forward_outcome_from_candles(
        candles,
        confirmation_time=conf,
        direction="LONG",
        entry=Decimal("102"),
        stop=Decimal("90"),
        target=Decimal("200"),
        forward_bars=5,
    )
    assert ret is not None
    assert hit_t is False
    assert hit_s is False

    a = SetupFingerprint(
        symbol="AAA",
        direction="LONG",
        confirmation_time=conf,
        quality_score=Decimal("70"),
        volume_thrust=Decimal("2"),
        retest_tightness=Decimal("0.5"),
        risk_percent=Decimal("2"),
        atr_percent=Decimal("2"),
        risk_reward_ratio=Decimal("2"),
        scan_run_id=1,
    )
    b = SetupFingerprint(
        symbol="BBB",
        direction="LONG",
        confirmation_time=conf - timedelta(days=30),
        quality_score=Decimal("72"),
        volume_thrust=Decimal("2"),
        retest_tightness=Decimal("0.5"),
        risk_percent=Decimal("2"),
        atr_percent=Decimal("2.1"),
        risk_reward_ratio=Decimal("2"),
        scan_run_id=2,
    )
    b_dup = SetupFingerprint(
        symbol="BBB",
        direction="LONG",
        confirmation_time=conf - timedelta(days=30),
        quality_score=Decimal("72"),
        volume_thrust=Decimal("2"),
        retest_tightness=Decimal("0.5"),
        risk_percent=Decimal("2"),
        atr_percent=Decimal("2.1"),
        risk_reward_ratio=Decimal("2"),
        scan_run_id=9,
    )
    c = SetupFingerprint(
        symbol="CCC",
        direction="SHORT",
        confirmation_time=conf - timedelta(days=10),
        quality_score=Decimal("70"),
        volume_thrust=Decimal("2"),
        retest_tightness=Decimal("0.5"),
        risk_percent=Decimal("2"),
        atr_percent=Decimal("2"),
        risk_reward_ratio=Decimal("2"),
        scan_run_id=3,
    )
    assert fingerprint_distance(a, c) == Decimal("999")
    ranked = rank_similar(a, [b, b_dup, c, a], limit=5)
    assert [item.symbol for item, _ in ranked] == ["BBB"]
    assert ranked[0][0].scan_run_id == 9
