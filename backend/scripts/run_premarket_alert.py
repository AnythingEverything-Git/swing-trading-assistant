"""Daily pre-market email alert and forming→confirmed status change alerts.

Designed to be run via Windows Task Scheduler or cron:
  - Daily before market open (e.g. 08:45 IST): sends summary of eligible setups
  - Periodically (e.g. every 30 min during market hours): detects forming→confirmed
    transitions and sends immediate email alerts

Usage:
    # Daily pre-market summary
    python scripts/run_premarket_alert.py --mode premarket --universe NIFTY_500

    # Confirmation watch (compares against last scan)
    python scripts/run_premarket_alert.py --mode confirmation-watch --universe NIFTY_500
"""
from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.api.routes.scan import to_scan_response
from app.application.alerts.composer import ScanAlert, compose_confirmation_alert, compose_scan_alert
from app.application.alerts.delivery import deliver_alert
from app.application.product.status_service import ProductStatusService
from app.application.scan.scan_presentation import present_scan
from app.application.scan.universe_scan_report_service import UniverseScanReportService
from app.application.strategy.strategy_evaluation_service import StrategyEvaluationService
from app.core.config import get_settings
from app.domain.strategy.strategy import BreakoutRetestConfirmationStrategy
from app.infrastructure.database.repositories.candle_repository import CandleRepository
from app.infrastructure.database.repositories.instrument_repository import InstrumentRepository
from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository
from app.infrastructure.database.session import create_engine, create_sessionmaker
from app.application.market_data.query_service import MarketDataQueryService
from app.application.market_data.demo_universe_seed_service import default_demo_seed_range
from app.infrastructure.universe import get_universe


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def _build_scan(universe_name: str, account_equity: Decimal | None, risk_percent: Decimal, top_n: int):
    """Run a scan and return (presented, response, scan_run, settings, engine)."""
    settings = get_settings()
    default_start, default_end = default_demo_seed_range()
    universe = get_universe(universe_name)
    snapshot = universe.get_snapshot()

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            query = MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
            evaluation = StrategyEvaluationService(query, BreakoutRetestConfirmationStrategy())
            report = await UniverseScanReportService(evaluation).scan_universe(
                universe, "1d", default_start, default_end
            )
            presented = present_scan(
                report,
                account_equity=account_equity,
                risk_percent=risk_percent if account_equity is not None else None,
                top_n=top_n,
            )
            product = ProductStatusService(CandleRepository(session), settings)
            status = await product.status("1d")
            started_at = datetime.now(timezone.utc)
            response = to_scan_response(
                presented=presented,
                universe_name=snapshot.name,
                universe_version=snapshot.version,
                timeframe="1d",
                start=default_start,
                end=default_end,
                scan_run_id=None,
                last_candle_time=status.last_candle_time,
            )
            finished_at = datetime.now(timezone.utc)
            scan_run = await ScanRunRepository(session).create(
                started_at=started_at,
                finished_at=finished_at,
                universe_date=default_end,
                universe_version=snapshot.version,
                parameters={
                    "universe_name": snapshot.name,
                    "timeframe": "1d",
                    "start": default_start.isoformat(),
                    "end": default_end.isoformat(),
                    "scheduled": True,
                    "data_source": response.data_source,
                },
                result_count=report.eligible_count,
                metadata={
                    "symbols_scanned": report.symbols_scanned,
                    "eligible_count": report.eligible_count,
                    "forming_count": report.forming_count,
                    "data_source": response.data_source,
                },
                result_payload=response.model_dump(mode="json"),
            )
            response.scan_run_id = scan_run.id
            await session.commit()
            return presented, response, scan_run, settings
    finally:
        await engine.dispose()


async def run_premarket(universe_name: str, account_equity: Decimal | None, risk_percent: Decimal, top_n: int):
    """Send daily pre-market summary email."""
    presented, response, scan_run, settings = await _build_scan(
        universe_name, account_equity, risk_percent, top_n
    )
    alert = compose_scan_alert(presented, universe_name=universe_name, data_claim=response.data_claim)
    today = date.today().isoformat()
    delivery = await deliver_alert(
        alert, settings, subject_override=f"TradePilot Pre-Market Alert — {universe_name} — {today}"
    )
    print(f"Pre-market alert sent. run_id={scan_run.id}")
    print(f"  eligible={response.eligible_count} forming={response.forming_count}")
    print(f"  email={delivery.email_sent} telegram={delivery.telegram_sent}")
    print(alert.body)


_LAST_ELIGIBLE_FILE = _BACKEND_ROOT / ".last_eligible_symbols.json"


async def run_confirmation_watch(universe_name: str, account_equity: Decimal | None, risk_percent: Decimal, top_n: int):
    """Compare current eligible set against last scan; email any new confirmations."""
    previous_eligible: set[str] = set()
    if _LAST_ELIGIBLE_FILE.exists():
        try:
            previous_eligible = set(json.loads(_LAST_ELIGIBLE_FILE.read_text()))
        except Exception:
            pass

    presented, response, scan_run, settings = await _build_scan(
        universe_name, account_equity, risk_percent, top_n
    )
    current_eligible = {opp.symbol for opp in response.opportunities}

    # Save current for next comparison
    _LAST_ELIGIBLE_FILE.write_text(json.dumps(sorted(current_eligible)))

    newly_confirmed = current_eligible - previous_eligible
    if not newly_confirmed:
        print(f"No new confirmations. eligible={len(current_eligible)}, previous={len(previous_eligible)}")
        return

    # Build a targeted alert for newly confirmed symbols
    new_lines = []
    for opp in response.opportunities:
        if opp.symbol in newly_confirmed:
            c = opp.candidate
            new_lines.append(
                f"{opp.symbol}  Entry {c.entry_price}  SL {c.stop_loss}  "
                f"Tgt {c.target}  R:R {c.risk_reward_ratio}"
            )

    alert = compose_confirmation_alert(symbols=sorted(newly_confirmed), lines=new_lines)
    delivery = await deliver_alert(
        alert, settings, subject_override=f"TradePilot: {len(newly_confirmed)} new confirmation(s)"
    )
    print(f"Confirmation alert sent for: {', '.join(sorted(newly_confirmed))}")
    print(f"  email={delivery.email_sent} telegram={delivery.telegram_sent}")


def main():
    parser = argparse.ArgumentParser(description="TradePilot email alert runner.")
    parser.add_argument("--mode", choices=["premarket", "confirmation-watch", "eod"], required=True)
    parser.add_argument("--universe", default="NIFTY_500")
    parser.add_argument("--account-equity", type=Decimal, default=None)
    parser.add_argument("--risk-percent", type=Decimal, default=Decimal("1"))
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()

    if args.mode == "premarket":
        _run_async(run_premarket(args.universe, args.account_equity, args.risk_percent, args.top_n))
    elif args.mode == "eod":
        # Delegate to scheduled scan EOD path (latest completed run).
        from run_scheduled_scan import run_eod_from_latest

        _run_async(run_eod_from_latest(universe_name=args.universe))
    else:
        _run_async(run_confirmation_watch(args.universe, args.account_equity, args.risk_percent, args.top_n))


if __name__ == "__main__":
    main()
