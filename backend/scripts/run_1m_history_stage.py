"""CLI: staged 1m history backfill (ephemeral worker or host).

Examples:

    python scripts/run_1m_history_stage.py --stage NIFTY_50
    python scripts/run_1m_history_stage.py --stage NIFTY_100_REMAINING --lookback-days 28

Requires MARKET_DATA_SOURCE=upstox, UPSTOX_ACCESS_TOKEN, DATABASE_URL.
Optional: TRADEPILOT_HEARTBEAT_BASE=http://172.31.x.x:8001 for Ops progress.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import selectors
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application.ops.history_backfill import (  # noqa: E402
    KNOWN_STAGES,
    default_history_window,
    resolve_stage_symbols,
    run_intraday_1m_history_backfill,
)
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.database.session import create_engine, create_sessionmaker  # noqa: E402
from app.infrastructure.market_data.factory import UpstoxProviderFactory  # noqa: E402
from app.infrastructure.market_data.source import normalize_market_data_source  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_1m_history_stage")


def _run_async(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def _heartbeat(base: str, *, status: str, detail: str, phase: str, running: bool) -> None:
    if not base:
        return
    url = base.rstrip("/") + "/api/v1/ops/schedulers/heartbeat"
    body = json.dumps(
        {
            "job_id": "host_1m_history",
            "status": status,
            "detail": detail[:320],
            "phase": phase,
            "running": running,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("heartbeat failed: %s", exc)


async def _main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    if normalize_market_data_source(settings.market_data_source) != "upstox":
        logger.error("Set MARKET_DATA_SOURCE=upstox")
        return 2

    stage = (args.stage or "SYMBOLS").strip().upper()
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = resolve_stage_symbols(stage)
    if not symbols:
        logger.error("No symbols resolved (stage=%s)", stage)
        return 2

    win_start, win_end = default_history_window(lookback_days=args.lookback_days)
    start = date.fromisoformat(args.start) if args.start else win_start
    end = date.fromisoformat(args.end) if args.end else win_end
    heartbeat_base = (args.heartbeat_base or "").strip()

    logger.info("Stage %s → %s symbols; range %s→%s", stage, len(symbols), start, end)
    _heartbeat(
        heartbeat_base,
        status="running",
        detail=f"Starting {stage} ({len(symbols)} symbols) {start}→{end}",
        phase=stage,
        running=True,
    )

    factory = UpstoxProviderFactory()
    provider = await factory.startup()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    async def on_progress(payload: dict) -> None:
        detail = str(payload.get("detail") or "")
        _heartbeat(
            heartbeat_base,
            status="running",
            detail=detail,
            phase=stage,
            running=True,
        )

    try:
        summary = await run_intraday_1m_history_backfill(
            None,
            stage=stage,
            symbols=symbols,
            start=start,
            end=end,
            pause_s=args.pause,
            sessionmaker=sessionmaker,
            provider=provider,
            on_progress=on_progress,
        )
    except Exception as exc:
        logger.exception("stage failed")
        _heartbeat(
            heartbeat_base,
            status="failed",
            detail=str(exc)[:240],
            phase=stage,
            running=False,
        )
        return 1
    finally:
        await factory.shutdown()
        await engine.dispose()

    detail = (
        f"done {summary.get('stage')} persisted={summary.get('persisted')} "
        f"failures={summary.get('failures')}"
    )
    _heartbeat(
        heartbeat_base,
        status="ok",
        detail=detail,
        phase=stage,
        running=False,
    )
    logger.info("%s", detail)
    return 0 if int(summary.get("failures") or 0) == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Staged 1m history backfill")
    parser.add_argument(
        "--stage",
        default="SYMBOLS",
        help=f"One of: {', '.join(KNOWN_STAGES)} (or a universe name). Ignored when --symbols is set.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols to backfill (skips stage resolution)",
    )
    parser.add_argument("--lookback-days", type=int, default=28)
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    parser.add_argument("--pause", type=float, default=0.2)
    parser.add_argument(
        "--heartbeat-base",
        default=None,
        help="Live API base for Ops heartbeats (e.g. http://172.31.0.249:8001)",
    )
    args = parser.parse_args()
    if not args.heartbeat_base:
        import os

        args.heartbeat_base = os.environ.get("TRADEPILOT_HEARTBEAT_BASE", "")
    raise SystemExit(_run_async(_main_async(args)))


if __name__ == "__main__":
    main()
