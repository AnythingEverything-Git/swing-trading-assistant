from datetime import datetime, timezone
from decimal import Decimal

from app.application.alerts.composer import compose_scan_alert
from app.application.narrative.template_narrator import eligible_narrative, invalidation_copy
from app.application.scan.opportunity_scan_service import EligibleOpportunity
from app.application.scan.quality_score import score_opportunity
from app.application.scan.scan_presentation import present_scan
from app.application.scan.universe_scan_report_service import UniverseScanReport
from app.domain.strategy.strategy import StrategyEvidence, TradeCandidate


def _evidence(**overrides) -> StrategyEvidence:
    payload = dict(
        resistance=Decimal("101.50"),
        breakout_candle_index=19,
        breakout_candle_time=datetime(2024, 1, 20, tzinfo=timezone.utc),
        retest_candle_index=20,
        retest_candle_time=datetime(2024, 1, 21, tzinfo=timezone.utc),
        confirmation_candle_index=21,
        confirmation_candle_time=datetime(2024, 1, 22, tzinfo=timezone.utc),
        atr_value=Decimal("2.50"),
        volume_sma_value=Decimal("1200"),
        breakout_volume=2400,
        retest_low=Decimal("100.80"),
        confirmation_volume=1800,
        decision="valid breakout -> retest -> confirmation",
    )
    payload.update(overrides)
    return StrategyEvidence(**payload)


def _candidate(symbol: str, entry="100.00", stop="98.00", target="104.00") -> TradeCandidate:
    return TradeCandidate(
        symbol=symbol,
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal(entry),
        stop_loss=Decimal(stop),
        target=Decimal(target),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="BreakoutRetestConfirmation",
    )


def test_quality_score_is_bounded_and_uses_evidence_only():
    quality = score_opportunity(_candidate("INFY"), _evidence())
    assert Decimal("0") <= quality.score <= Decimal("100")
    assert quality.volume_thrust == Decimal("2.00")


def test_present_scan_ranks_higher_volume_thrust_first():
    weak = EligibleOpportunity(
        symbol="WEAK",
        candidate=_candidate("WEAK"),
        evidence=_evidence(breakout_volume=1300, confirmation_volume=1200),
    )
    strong = EligibleOpportunity(
        symbol="STRONG",
        candidate=_candidate("STRONG"),
        evidence=_evidence(breakout_volume=3600, confirmation_volume=3000),
    )
    report = UniverseScanReport(
        symbols_scanned=2,
        eligible_count=2,
        no_setup_count=0,
        unavailable_count=0,
        error_count=0,
        opportunities=(weak, strong),
        issues=(),
    )
    presented = present_scan(report, top_n=1)
    assert presented.opportunities[0].opportunity.symbol == "STRONG"
    assert presented.top[0].opportunity.symbol == "STRONG"
    assert len(presented.top) == 1


def test_narrative_only_uses_candidate_and_evidence_numbers():
    candidate = _candidate("INFY", entry="219.78", stop="210.00", target="239.34")
    evidence = _evidence()
    text = eligible_narrative(candidate, evidence)
    assert "INFY" in text
    assert "219.78" in text
    assert "239.34" in text
    assert "invent" not in text.lower()
    assert "₹101.50" in invalidation_copy(evidence)


def test_short_quality_and_narrative_use_support_geometry():
    candidate = TradeCandidate(
        symbol="SHORTCO",
        timeframe="1d",
        direction="SHORT",
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("102.00"),
        target=Decimal("96.00"),
        risk_per_share=Decimal("0"),
        reward=Decimal("0"),
        risk_reward_ratio=Decimal("0"),
        setup_name="BreakdownRetestConfirmation",
    )
    evidence = _evidence(
        resistance=Decimal("101.00"),
        retest_low=Decimal("101.40"),
        decision="valid breakdown -> retest -> confirmation",
        direction="SHORT",
    )
    quality = score_opportunity(candidate, evidence)
    assert Decimal("0") <= quality.score <= Decimal("100")
    assert "support" in quality.reason
    text = eligible_narrative(candidate, evidence)
    assert "breakdown" in text.lower()
    assert "support" in text.lower()
    assert "Short" in invalidation_copy(evidence)


def test_alert_mentions_data_claim_and_top():
    opp = EligibleOpportunity(symbol="INFY", candidate=_candidate("INFY"), evidence=_evidence())
    report = UniverseScanReport(
        symbols_scanned=1,
        eligible_count=1,
        no_setup_count=0,
        unavailable_count=0,
        error_count=0,
        opportunities=(opp,),
        issues=(),
    )
    presented = present_scan(report, top_n=5)
    alert = compose_scan_alert(
        presented, universe_name="NIFTY_50", data_claim="Demo candles — not live market data"
    )
    assert "Demo candles" in alert.body
    assert "INFY" in alert.body
    assert "not investment advice" in alert.body.lower()
