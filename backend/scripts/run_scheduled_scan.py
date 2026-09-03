"""Run a universe scan, persist the ranked result, and deliver the alert payload.

Works on demo candles today. After MARKET_DATA_SOURCE=upstox + refresh, the same
command produces live post-close alerts.

    python scripts/run_scheduled_scan.py --universe NIFTY_50
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.api.routes.scan import to_scan_response
from app.application.alerts import compose_scan_alert, deliver_alert
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


def _parse_iso_date(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def run_scan(
    *,
    universe_name: str,
    start: datetime | None,
    end: datetime | None,
    account_equity: Decimal | None,
    risk_percent: Decimal,
    top_n: int,
) -> None:
    settings = get_settings()
    default_start, default_end = default_demo_seed_range()
    resolved_end = end or default_end
    resolved_start = start or default_start
    universe = get_universe(universe_name)
    snapshot = universe.get_snapshot()

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            query = MarketDataQueryService(InstrumentRepository(session), CandleRepository(session))
            evaluation = StrategyEvaluationService(query, BreakoutRetestConfirmationStrategy())
            report = await UniverseScanReportService(evaluation).scan_universe(
                universe, "1d", resolved_start, resolved_end
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
                start=resolved_start,
                end=resolved_end,
                scan_run_id=None,
                last_candle_time=status.last_candle_time,
            )
            finished_at = datetime.now(timezone.utc)
            scan_run = await ScanRunRepository(session).create(
                started_at=started_at,
                finished_at=finished_at,
                universe_date=resolved_end,
                universe_version=snapshot.version,
                parameters={
                    "universe_name": snapshot.name,
                    "timeframe": "1d",
                    "start": resolved_start.isoformat(),
                    "end": resolved_end.isoformat(),
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
            alert = compose_scan_alert(
                presented, universe_name=snapshot.name, data_claim=response.data_claim
            )
            delivery = await deliver_alert(alert, settings)
            await session.commit()
            print(f"Scheduled scan complete run_id={scan_run.id} source={response.data_source}")
            print(f"  eligible={report.eligible_count} forming={report.forming_count} top={len(presented.top)}")
            print(f"  alert_logged={delivery.logged} telegram={delivery.telegram_sent}")
            print(alert.body)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled TradePilot universe scan + alert.")
    parser.add_argument("--universe", default="NIFTY_500")
    parser.add_argument("--start", type=_parse_iso_date, default=None)
    parser.add_argument("--end", type=_parse_iso_date, default=None)
    parser.add_argument("--account-equity", type=Decimal, default=None)
    parser.add_argument("--risk-percent", type=Decimal, default=Decimal("1"))
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()
    _run_async(
        run_scan(
            universe_name=args.universe,
            start=args.start,
            end=args.end,
            account_equity=args.account_equity,
            risk_percent=args.risk_percent,
            top_n=args.top_n,
        )
    )


if __name__ == "__main__":
    main()
