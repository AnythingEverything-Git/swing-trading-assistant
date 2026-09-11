"""Nifty 500 (desk) readiness SLOs — provider-max aware, not wall-clock alone."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.domain.intraday.session_calendar import is_weekday
from app.infrastructure.database.models.candle import CandleORM
from app.infrastructure.database.models.instrument import InstrumentORM
from app.infrastructure.market_data.instrument_key_map import load_default_nse_instrument_key_map
from app.infrastructure.market_data.source import live_ready, normalize_market_data_source
from app.infrastructure.universe import get_universe

IST = ZoneInfo("Asia/Kolkata")

GateStatus = Literal["green", "amber", "red", "skipped"]
OverallStatus = Literal["green", "amber", "red"]

COVERAGE_PASS_PCT = 99.0
MUTEX_STUCK_MINUTES = 45
HISTORY_LOOKBACK_DAYS = 40
HISTORY_MIN_SESSIONS = 14
# Known BE-series constituents that historically lacked EQ keys.
CRITICAL_KEY_SYMBOLS = ("HEG", "HFCL")


@dataclass(frozen=True)
class ReadinessGate:
    id: str
    label: str
    status: GateStatus
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class ReadinessReport:
    universe: str
    ready: bool
    status: OverallStatus
    as_of: datetime
    provider_1d_max: datetime | None
    calendar_1d_expected: date | None
    gates: tuple[ReadinessGate, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe": self.universe,
            "ready": self.ready,
            "status": self.status,
            "as_of": self.as_of.isoformat(),
            "provider_1d_max": self.provider_1d_max.isoformat() if self.provider_1d_max else None,
            "calendar_1d_expected": self.calendar_1d_expected.isoformat()
            if self.calendar_1d_expected
            else None,
            "gates": [g.to_dict() for g in self.gates],
            "recommendations": list(self.recommendations),
        }


def _pct(numer: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return round(100.0 * numer / denom, 2)


def _overall(gates: list[ReadinessGate]) -> OverallStatus:
    statuses = {g.status for g in gates if g.status != "skipped"}
    if "red" in statuses:
        return "red"
    if "amber" in statuses:
        return "amber"
    return "green"


def _expected_calendar_1d(now_ist: datetime) -> date | None:
    """Last completed session we hope Upstox has published as 1d (not a hard SLO)."""
    d = now_ist.date()
    if not is_weekday(d):
        # roll back to Friday
        while not is_weekday(d):
            d = d - timedelta(days=1)
        return d
    # Before ~18:00 IST on a trading day, expect prior session; after, expect today if published.
    if now_ist.hour < 18:
        d = d - timedelta(days=1)
        while not is_weekday(d):
            d = d - timedelta(days=1)
    return d


async def _max_ts_by_symbol(
    session: AsyncSession,
    symbols: list[str],
    timeframe: str,
) -> dict[str, datetime]:
    if not symbols:
        return {}
    stmt = (
        select(InstrumentORM.symbol, func.max(CandleORM.timestamp))
        .join(CandleORM, CandleORM.instrument_id == InstrumentORM.id)
        .where(InstrumentORM.symbol.in_(symbols))
        .where(CandleORM.timeframe == timeframe)
        .group_by(InstrumentORM.symbol)
    )
    result = await session.execute(stmt)
    out: dict[str, datetime] = {}
    for sym, ts in result.fetchall():
        if sym and ts is not None:
            out[str(sym).strip().upper()] = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return out


async def _history_session_counts(
    session: AsyncSession,
    symbols: list[str],
    *,
    lookback_days: int = HISTORY_LOOKBACK_DAYS,
) -> dict[str, int]:
    """Distinct IST calendar days with any 1m bar in the lookback (RVOL proxy)."""
    if not symbols:
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    # Postgres: cast timestamptz to IST date; SQLite tests use simpler date().
    bind = session.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
    if dialect == "postgresql":
        day_expr = func.date(func.timezone("Asia/Kolkata", CandleORM.timestamp))
    else:
        day_expr = func.date(CandleORM.timestamp)

    stmt = (
        select(InstrumentORM.symbol, func.count(func.distinct(day_expr)))
        .join(CandleORM, CandleORM.instrument_id == InstrumentORM.id)
        .where(InstrumentORM.symbol.in_(symbols))
        .where(CandleORM.timeframe == "1m")
        .where(CandleORM.timestamp >= cutoff)
        .group_by(InstrumentORM.symbol)
    )
    result = await session.execute(stmt)
    return {str(sym).strip().upper(): int(cnt or 0) for sym, cnt in result.fetchall() if sym}


def _gate_live(settings: Settings) -> ReadinessGate:
    ready = live_ready(settings)
    source = normalize_market_data_source(settings.market_data_source)
    token = bool(getattr(settings, "upstox_access_token", None) and str(settings.upstox_access_token).strip())
    if ready:
        status: GateStatus = "green"
        detail = "live_ready=true"
    elif source != "upstox":
        status = "red"
        detail = f"MARKET_DATA_SOURCE={source} (need upstox)"
    elif not token:
        status = "red"
        detail = "UPSTOX_ACCESS_TOKEN missing — mint token → restart_api_token.sh"
    else:
        status = "red"
        detail = "live_ready=false"
    return ReadinessGate(
        id="live",
        label="Live token / source",
        status=status,
        detail=detail,
        metrics={"live_ready": ready, "data_source": source, "token_configured": token},
    )


def _gate_swing_1d(
    *,
    symbols: list[str],
    max_1d: dict[str, datetime],
    provider_max: datetime | None,
    calendar_expected: date | None,
    now_ist: datetime,
) -> ReadinessGate:
    total = len(symbols)
    at_max = 0
    if provider_max is not None:
        for sym in symbols:
            ts = max_1d.get(sym)
            if ts is not None and ts >= provider_max:
                at_max += 1
    pct = _pct(at_max, total)
    no_1d = sum(1 for s in symbols if s not in max_1d)
    metrics = {
        "total": total,
        "at_provider_max": at_max,
        "pct_at_provider_max": pct,
        "no_1d": no_1d,
        "threshold_pct": COVERAGE_PASS_PCT,
    }

    if total == 0:
        return ReadinessGate("swing_1d", "Swing 1d (provider-max)", "red", "Empty universe", metrics)

    if pct < COVERAGE_PASS_PCT:
        return ReadinessGate(
            id="swing_1d",
            label="Swing 1d (provider-max)",
            status="red",
            detail=f"{pct}% at provider_1d_max (need ≥{COVERAGE_PASS_PCT}%) — run paced 1d retry",
            metrics=metrics,
        )

    # Aligned to what Upstox has given us; may still lag calendar.
    provider_day = provider_max.astimezone(IST).date() if provider_max else None
    if (
        calendar_expected is not None
        and provider_day is not None
        and provider_day < calendar_expected
        and now_ist.weekday() < 5
    ):
        return ReadinessGate(
            id="swing_1d",
            label="Swing 1d (provider-max)",
            status="amber",
            detail=(
                f"{pct}% at provider_1d_max={provider_day.isoformat()} but calendar expects "
                f"{calendar_expected.isoformat()} (Upstox daily lag — not our gap)"
            ),
            metrics=metrics,
        )

    return ReadinessGate(
        id="swing_1d",
        label="Swing 1d (provider-max)",
        status="green",
        detail=f"{pct}% of universe at provider_1d_max",
        metrics=metrics,
    )


def _gate_history_1m(
    *,
    symbols: list[str],
    session_counts: dict[str, int],
) -> ReadinessGate:
    total = len(symbols)
    ok = sum(1 for s in symbols if session_counts.get(s, 0) >= HISTORY_MIN_SESSIONS)
    pct = _pct(ok, total)
    metrics = {
        "total": total,
        "with_min_sessions": ok,
        "pct": pct,
        "min_sessions": HISTORY_MIN_SESSIONS,
        "lookback_days": HISTORY_LOOKBACK_DAYS,
        "threshold_pct": COVERAGE_PASS_PCT,
    }
    if pct < COVERAGE_PASS_PCT:
        return ReadinessGate(
            id="history_1m",
            label="Intraday 1m history (RVOL)",
            status="red",
            detail=f"{pct}% have ≥{HISTORY_MIN_SESSIONS} 1m sessions in {HISTORY_LOOKBACK_DAYS}d",
            metrics=metrics,
        )
    return ReadinessGate(
        id="history_1m",
        label="Intraday 1m history (RVOL)",
        status="green",
        detail=f"{pct}% have ≥{HISTORY_MIN_SESSIONS} prior 1m session days",
        metrics=metrics,
    )


def _gate_today_1m(
    *,
    symbols: list[str],
    max_1m: dict[str, datetime],
    now_ist: datetime,
) -> ReadinessGate:
    today = now_ist.date()
    metrics: dict[str, Any] = {"session_date": today.isoformat()}
    if not is_weekday(today):
        return ReadinessGate(
            id="today_1m",
            label="Today 1m",
            status="skipped",
            detail="Weekend — today 1m N/A",
            metrics=metrics,
        )

    minutes = now_ist.hour * 60 + now_ist.minute
    if minutes < (9 * 60 + 25):
        return ReadinessGate(
            id="today_1m",
            label="Today 1m",
            status="skipped",
            detail="Before 09:25 IST — gate not yet required",
            metrics=metrics,
        )

    on_today = 0
    for sym in symbols:
        ts = max_1m.get(sym)
        if ts is None:
            continue
        if ts.astimezone(IST).date() == today:
            on_today += 1
    pct = _pct(on_today, len(symbols))
    metrics.update(
        {
            "on_today": on_today,
            "total": len(symbols),
            "pct_on_today": pct,
            "threshold_pct": COVERAGE_PASS_PCT,
        }
    )
    if pct < COVERAGE_PASS_PCT:
        # Soften early session: amber until ~10:00 while cron may still be running
        status: GateStatus = "amber" if minutes < (10 * 60) else "red"
        return ReadinessGate(
            id="today_1m",
            label="Today 1m",
            status=status,
            detail=f"{pct}% have last_1m on {today.isoformat()} — run run_1m_today.sh / perfect-today",
            metrics=metrics,
        )
    return ReadinessGate(
        id="today_1m",
        label="Today 1m",
        status="green",
        detail=f"{pct}% have last_1m in today's session",
        metrics=metrics,
    )


def _gate_keys(*, symbols: list[str], max_1d: dict[str, datetime]) -> ReadinessGate:
    try:
        key_map = load_default_nse_instrument_key_map()
    except Exception as exc:
        return ReadinessGate(
            id="keys",
            label="Instrument keys",
            status="red",
            detail=f"Failed to load instrument key map: {exc}",
            metrics={},
        )

    missing_keys = [s for s in symbols if s not in key_map]
    no_candles = [s for s in symbols if s not in max_1d]
    critical_missing = [s for s in CRITICAL_KEY_SYMBOLS if s in symbols and s not in key_map]
    metrics = {
        "missing_keys": len(missing_keys),
        "no_candles": len(no_candles),
        "critical_missing": critical_missing,
        "mapped": len(key_map),
    }
    if critical_missing or len(no_candles) > max(3, int(0.01 * len(symbols))):
        return ReadinessGate(
            id="keys",
            label="Instrument keys / candles",
            status="red",
            detail=(
                f"no_candles={len(no_candles)} missing_keys={len(missing_keys)}"
                + (f" critical={critical_missing}" if critical_missing else "")
            ),
            metrics=metrics,
        )
    if missing_keys:
        return ReadinessGate(
            id="keys",
            label="Instrument keys / candles",
            status="amber",
            detail=f"{len(missing_keys)} symbols without Upstox keys (rebuild EQ+BE map)",
            metrics=metrics,
        )
    return ReadinessGate(
        id="keys",
        label="Instrument keys / candles",
        status="green",
        detail=f"no_candles≈0 ({len(no_candles)}); critical BE keys present",
        metrics=metrics,
    )


def _gate_host(
    *,
    refresh_mutex_held: bool,
    refresh_running_since: datetime | None,
    history_backfill_running: bool,
) -> ReadinessGate:
    metrics: dict[str, Any] = {
        "refresh_mutex_held": refresh_mutex_held,
        "history_backfill_running": history_backfill_running,
        "stuck_threshold_min": MUTEX_STUCK_MINUTES,
    }
    if refresh_mutex_held and refresh_running_since is not None:
        age_min = (datetime.now(timezone.utc) - refresh_running_since.astimezone(timezone.utc)).total_seconds() / 60
        metrics["mutex_held_minutes"] = round(age_min, 1)
        if age_min > MUTEX_STUCK_MINUTES:
            return ReadinessGate(
                id="host",
                label="Host / refresh mutex",
                status="red",
                detail=f"refresh mutex held {age_min:.0f}m (>{MUTEX_STUCK_MINUTES}m) — check API / reboot",
                metrics=metrics,
            )
    if refresh_mutex_held:
        return ReadinessGate(
            id="host",
            label="Host / refresh mutex",
            status="amber",
            detail="refresh mutex currently held (job in progress)",
            metrics=metrics,
        )
    return ReadinessGate(
        id="host",
        label="Host / refresh mutex",
        status="green",
        detail="mutex free" + (" · history backfill running" if history_backfill_running else ""),
        metrics=metrics,
    )


def _recommendations(gates: list[ReadinessGate], status: OverallStatus) -> list[str]:
    recs: list[str] = []
    by_id = {g.id: g for g in gates}
    if by_id.get("live") and by_id["live"].status == "red":
        recs.append("Mint Upstox token, update .env UPSTOX_ACCESS_TOKEN, run restart_api_token.sh")
    if by_id.get("swing_1d") and by_id["swing_1d"].status == "red":
        recs.append("Run ops/vps/run_1d_n500_paced.sh (17:00 cron) to align behind symbols to provider_max")
    if by_id.get("swing_1d") and by_id["swing_1d"].status == "amber":
        recs.append("Amber is provider lag — stale_risk may stay Medium until Upstox publishes newer 1d")
    if by_id.get("today_1m") and by_id["today_1m"].status in ("red", "amber"):
        recs.append("Run ops/vps/run_1m_today.sh or run_nifty500_perfect_today.sh")
    if by_id.get("history_1m") and by_id["history_1m"].status == "red":
        recs.append("Use ephemeral worker staged 1m history (ops/vps/worker/) — destroy after")
    if by_id.get("keys") and by_id["keys"].status != "green":
        recs.append("Weekly: run_universe_rebuild.sh + refresh_instrument_key_map.py (EQ+BE)")
    if by_id.get("host") and by_id["host"].status == "red":
        recs.append("Watchdog should restart api; if stuck, docker compose restart api or reboot host")
    if status == "green":
        recs.append("Desk ready — prefer NIFTY_500 board; avoid NSE_ALL auto-refresh on t3.micro")
    return recs


async def evaluate_readiness(
    session: AsyncSession,
    *,
    universe: str = "NIFTY_500",
    settings: Settings | None = None,
    refresh_mutex_held: bool = False,
    refresh_running_since: datetime | None = None,
    history_backfill_running: bool = False,
) -> ReadinessReport:
    settings = settings or get_settings()
    universe_name = (universe or "NIFTY_500").strip().upper() or "NIFTY_500"
    snap = get_universe(universe_name).get_snapshot()
    symbols = [str(s).strip().upper() for s in snap.symbols]
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)
    calendar_expected = _expected_calendar_1d(now_ist)

    max_1d = await _max_ts_by_symbol(session, symbols, "1d")
    max_1m = await _max_ts_by_symbol(session, symbols, "1m")
    provider_max = max(max_1d.values()) if max_1d else None
    session_counts = await _history_session_counts(session, symbols)

    gates = [
        _gate_live(settings),
        _gate_swing_1d(
            symbols=symbols,
            max_1d=max_1d,
            provider_max=provider_max,
            calendar_expected=calendar_expected,
            now_ist=now_ist,
        ),
        _gate_history_1m(symbols=symbols, session_counts=session_counts),
        _gate_today_1m(symbols=symbols, max_1m=max_1m, now_ist=now_ist),
        _gate_keys(symbols=symbols, max_1d=max_1d),
        _gate_host(
            refresh_mutex_held=refresh_mutex_held,
            refresh_running_since=refresh_running_since,
            history_backfill_running=history_backfill_running,
        ),
    ]
    status = _overall(gates)
    return ReadinessReport(
        universe=universe_name,
        ready=status != "red",
        status=status,
        as_of=now_utc,
        provider_1d_max=provider_max,
        calendar_1d_expected=calendar_expected,
        gates=tuple(gates),
        recommendations=tuple(_recommendations(gates, status)),
    )


__all__ = [
    "ReadinessGate",
    "ReadinessReport",
    "evaluate_readiness",
    "COVERAGE_PASS_PCT",
    "MUTEX_STUCK_MINUTES",
]
