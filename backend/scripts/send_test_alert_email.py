"""Send a one-off test email using the real TradePilot alert template.

Prefers a live Nifty 50 scan payload; falls back to a sample templated alert.

    python scripts/send_test_alert_email.py
"""
from __future__ import annotations

import asyncio
import selectors
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.alerts.composer import compose_scan_alert
from app.application.alerts.email_delivery import deliver_email_alert, resolve_smtp_target
from app.core.config import get_settings


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def _sample_alert():
    from app.application.scan.opportunity_scan_service import EligibleOpportunity
    from app.application.scan.quality_score import QualityScore
    from app.application.scan.scan_presentation import PresentedForming, PresentedOpportunity, PresentedScan
    from app.application.scan.universe_scan_report_service import UniverseScanReport
    from app.domain.strategy.strategy import FormingSetup, StrategyEvidence, TradeCandidate

    now = datetime.now(timezone.utc)
    candidate = TradeCandidate(
        symbol="INFY",
        timeframe="1d",
        direction="LONG",
        entry_price=Decimal("1520.00"),
        stop_loss=Decimal("1485.00"),
        target=Decimal("1590.00"),
        risk_per_share=Decimal("35.00"),
        reward=Decimal("70.00"),
        risk_reward_ratio=Decimal("2.00"),
        setup_name="BreakoutRetestConfirmation",
    )
    evidence = StrategyEvidence(
        resistance=Decimal("1510.00"),
        breakout_candle_index=18,
        breakout_candle_time=now,
        retest_candle_index=19,
        retest_candle_time=now,
        confirmation_candle_index=20,
        confirmation_candle_time=now,
        atr_value=Decimal("18.50"),
        volume_sma_value=Decimal("1200000"),
        breakout_volume=2400000,
        retest_low=Decimal("1498.00"),
        confirmation_volume=1800000,
        decision="valid breakout -> retest -> confirmation",
    )
    opportunity = EligibleOpportunity(symbol="INFY", candidate=candidate, evidence=evidence)
    presented_opp = PresentedOpportunity(
        opportunity=opportunity,
        quality=QualityScore(
            score=Decimal("82.50"),
            volume_thrust=Decimal("2.00"),
            confirmation_volume_ratio=Decimal("1.50"),
            retest_tightness=Decimal("0.65"),
            risk_percent=Decimal("2.30"),
            reason="sample quality",
        ),
        rank=1,
        narrative="Sample INFY setup for email template verification.",
        invalidation="Close below retest low invalidates.",
        quantity=57,
        risk_amount=Decimal("1995.00"),
    )
    forming = FormingSetup(
        symbol="TCS",
        timeframe="1d",
        stage="AWAITING_CONFIRMATION",
        resistance=Decimal("4100.00"),
        breakout_candle_index=17,
        breakout_candle_time=now,
        breakout_volume=1500000,
        atr_value=Decimal("45.00"),
        volume_sma_value=Decimal("900000"),
        bars_elapsed=2,
        bars_remaining=1,
        reason="Breakout + retest complete; waiting confirmation",
        retest_candle_index=18,
        retest_candle_time=now,
        retest_low=Decimal("4080.00"),
    )
    report = UniverseScanReport(
        symbols_scanned=500,
        eligible_count=1,
        no_setup_count=480,
        unavailable_count=10,
        error_count=0,
        opportunities=(opportunity,),
        issues=(),
        forming_count=1,
        forming=(forming,),
    )
    presented = PresentedScan(
        report=report,
        opportunities=(presented_opp,),
        top=(presented_opp,),
        forming=(PresentedForming(forming=forming, narrative="TCS awaiting confirmation"),),
    )
    return compose_scan_alert(
        presented,
        universe_name="NIFTY_500",
        data_claim="Live Upstox 1d candles",
    )


async def _alert_from_latest_scan():
    from app.api.routes.scan import to_scan_response
    from app.application.market_data.demo_universe_seed_service import default_demo_seed_range
    from app.application.market_data.query_service import MarketDataQueryService
    from app.application.product.status_service import ProductStatusService
    from app.application.scan.scan_presentation import present_scan
    from app.application.scan.universe_scan_report_service import UniverseScanReportService
    from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
    from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy
    from app.infrastructure.database.repositories.candle_repository import CandleRepository
    from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
    from app.infrastructure.database.session import create_engine, create_sessionmaker
    from app.infrastructure.universe import get_universe

    settings = get_settings()
    start, end = default_demo_seed_range()
    universe = get_universe("NIFTY_50")
    snapshot = universe.get_snapshot()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            query = MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
            evaluation = StrategyEvaluationService(query, BreakoutRetestConfirmationStrategy())
            report = await UniverseScanReportService(evaluation).scan_universe(
                universe, "1d", start, end
            )
            presented = present_scan(
                report,
                account_equity=Decimal("200000"),
                risk_percent=Decimal("1"),
                top_n=5,
            )
            product = ProductStatusService(CandleRepository(session), settings)
            status = await product.status("1d")
            response = to_scan_response(
                presented=presented,
                universe_name=snapshot.name,
                universe_version=snapshot.version,
                timeframe="1d",
                start=start,
                end=end,
                scan_run_id=None,
                last_candle_time=status.last_candle_time,
            )
            alert = compose_scan_alert(
                presented,
                universe_name=snapshot.name,
                data_claim=response.data_claim,
            )
            return alert, f"live scan eligible={report.eligible_count} forming={report.forming_count}"
    finally:
        await engine.dispose()


async def main() -> None:
    settings = get_settings()
    target = resolve_smtp_target(settings)
    if isinstance(target, str):
        print(target)
        raise SystemExit(1)

    print(f"Provider: {target.provider}")
    print(f"Host:     {target.host}:{target.port}")
    print(f"From:     {target.from_addr}")
    print(f"To:       {', '.join(target.recipients)}")

    source = "sample template"
    try:
        alert, source = await _alert_from_latest_scan()
    except Exception as exc:
        print(f"Live scan unavailable ({exc}); using sample template.")
        alert = _sample_alert()

    print(f"Source:   {source}")
    print(f"Subject:  {alert.title}")
    print(f"HTML:     {'yes' if alert.html_body else 'no'}")

    result = await deliver_email_alert(
        alert,
        settings=settings,
        subject_override=f"[TEST] {alert.title}",
    )
    print(f"Sent:     {result.email_sent}")
    print(f"Detail:   {result.detail}")
    if not result.email_sent:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_async(main())
