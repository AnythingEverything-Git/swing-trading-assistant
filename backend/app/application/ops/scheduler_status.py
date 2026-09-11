"""In-memory registry for in-app + host scheduler job status."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings, get_settings
from app.infrastructure.market_data.source import normalize_market_data_source

JOB_IDS = (
    "inapp_1d",
    "inapp_1m",
    "cron_1m_today",
    "cron_1d",
    "cron_1d_paced",
    "cron_readiness",
    "cron_watchdog",
    "cron_universe",
    "host_catchup",
    "host_1m_history",
)

KNOWN_JOB_IDS = frozenset(JOB_IDS)

# Jobs the API can start in-process (manual Run Now).
RUNNABLE_JOB_IDS = frozenset(
    {"inapp_1d", "inapp_1m", "cron_1d", "cron_1m_today", "host_1m_history"}
)


@dataclass
class SchedulerJobStatus:
    job_id: str
    label: str
    source: str  # inapp | cron | host
    enabled: bool = True
    schedule: str = ""
    universe: str | None = None
    running: bool = False
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_status: str = "unknown"  # ok | failed | skipped | unknown | running
    last_detail: str | None = None
    phase: str | None = None
    can_run: bool = False
    progress_done: int | None = None
    progress_total: int | None = None
    progress_current: str | None = None
    progress_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        for key in ("next_run_at", "last_started_at", "last_finished_at"):
            val = raw.get(key)
            if isinstance(val, datetime):
                raw[key] = val.isoformat()
        raw["can_run"] = self.job_id in RUNNABLE_JOB_IDS
        if self.progress_done is not None and self.progress_total:
            raw["progress_pct"] = round(100.0 * self.progress_done / self.progress_total, 1)
        return raw


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_jobs() -> dict[str, SchedulerJobStatus]:
    return {
        "inapp_1d": SchedulerJobStatus(
            job_id="inapp_1d",
            label="In-app 1d watermark",
            source="inapp",
            schedule="Weekdays MARKET_DATA_REFRESH_TIME IST",
            can_run=True,
        ),
        "inapp_1m": SchedulerJobStatus(
            job_id="inapp_1m",
            label="In-app 1m active set",
            source="inapp",
            schedule="Mon–Fri 09:10–15:15 IST",
            can_run=True,
        ),
        "cron_1m_today": SchedulerJobStatus(
            job_id="cron_1m_today",
            label="Cron 1m today",
            source="cron",
            schedule="Weekdays 09:25 IST",
            universe="NSE_ALL",
            enabled=True,
            can_run=True,
        ),
        "cron_1d": SchedulerJobStatus(
            job_id="cron_1d",
            label="Cron 1d safety watermark",
            source="cron",
            schedule="Weekdays 16:45 IST",
            universe="NSE_ALL",
            enabled=True,
            can_run=True,
        ),
        "cron_1d_paced": SchedulerJobStatus(
            job_id="cron_1d_paced",
            label="Cron paced 1d N500 retry",
            source="cron",
            schedule="Weekdays 17:00 IST",
            universe="NIFTY_500",
            enabled=True,
            can_run=False,
        ),
        "cron_readiness": SchedulerJobStatus(
            job_id="cron_readiness",
            label="Cron Nifty 500 readiness check",
            source="cron",
            schedule="Weekdays 09:35 / 12:00 / 16:50 IST",
            universe="NIFTY_500",
            enabled=True,
            can_run=False,
        ),
        "cron_watchdog": SchedulerJobStatus(
            job_id="cron_watchdog",
            label="API /health watchdog",
            source="cron",
            schedule="Every 5 min",
            enabled=True,
            can_run=False,
        ),
        "cron_universe": SchedulerJobStatus(
            job_id="cron_universe",
            label="Cron NSE universe rebuild",
            source="cron",
            schedule="Sunday 10:00 IST",
            universe="NSE_ALL",
            enabled=True,
            can_run=False,
        ),
        "host_catchup": SchedulerJobStatus(
            job_id="host_catchup",
            label="Host catch-up / perfect-today",
            source="host",
            schedule="Manual / nohup",
            universe="NSE_ALL",
            enabled=True,
            last_status="unknown",
            can_run=False,
        ),
        "host_1m_history": SchedulerJobStatus(
            job_id="host_1m_history",
            label="1m history backfill (RVOL)",
            source="host",
            schedule="Manual — ~20–25 trading days of 1m",
            universe="NSE_ALL",
            enabled=True,
            last_status="unknown",
            can_run=True,
        ),
    }


def ensure_registry(app_state: Any) -> dict[str, SchedulerJobStatus]:
    """Return (and create if needed) the scheduler registry on app.state."""
    reg = getattr(app_state, "scheduler_registry", None)
    if not isinstance(reg, dict) or not reg:
        reg = _default_jobs()
        app_state.scheduler_registry = reg
    else:
        # Merge newly added job definitions without wiping live state.
        for job_id, default in _default_jobs().items():
            if job_id not in reg:
                reg[job_id] = default
    if not isinstance(getattr(app_state, "scheduler_enabled_overrides", None), dict):
        app_state.scheduler_enabled_overrides = {}
    return reg


def _apply_overrides(app_state: Any) -> None:
    reg = ensure_registry(app_state)
    overrides: dict[str, bool] = getattr(app_state, "scheduler_enabled_overrides", {}) or {}
    for job_id, enabled in overrides.items():
        if job_id not in reg:
            continue
        job = reg[job_id]
        job.enabled = bool(enabled)
        if enabled and job.last_status == "skipped":
            job.last_status = "unknown"
            if job.last_detail and ("Disabled" in job.last_detail or "INTRADAY" in job.last_detail):
                job.last_detail = "Enabled via Ops"


def set_job_enabled(app_state: Any, job_id: str, enabled: bool) -> SchedulerJobStatus:
    if job_id not in KNOWN_JOB_IDS:
        raise ValueError(f"Unknown scheduler job_id: {job_id}")
    ensure_registry(app_state)
    overrides = app_state.scheduler_enabled_overrides
    overrides[job_id] = bool(enabled)
    _apply_overrides(app_state)
    job = app_state.scheduler_registry[job_id]
    job.last_detail = f"{'Enabled' if enabled else 'Disabled'} via Ops"
    return job


def is_job_enabled(app_state: Any, job_id: str) -> bool:
    ensure_registry(app_state)
    _apply_overrides(app_state)
    job = app_state.scheduler_registry.get(job_id)
    return bool(job and job.enabled)


def seed_registry_from_settings(app_state: Any, settings: Settings | None = None) -> dict[str, SchedulerJobStatus]:
    """Apply config snapshot to in-app + cron rows (respects Ops enable overrides)."""
    from app.application.market_data.refresh_scheduler import scheduler_should_run

    cfg = settings or get_settings()
    reg = ensure_registry(app_state)
    overrides: dict[str, bool] = getattr(app_state, "scheduler_enabled_overrides", {}) or {}
    inapp_ok = scheduler_should_run(cfg)
    refresh_time = getattr(cfg, "market_data_refresh_time", "16:15") or "16:15"
    universe_1d = getattr(cfg, "market_data_refresh_universe", "NSE_ALL") or "NSE_ALL"
    universe_1m = getattr(cfg, "intraday_1m_refresh_universe", "NIFTY_50") or "NIFTY_50"
    limit_1m = int(getattr(cfg, "intraday_1m_refresh_limit", 50) or 50)
    interval = max(60, int(getattr(cfg, "intraday_1m_refresh_interval_sec", 300) or 300))
    one_m_enabled = bool(getattr(cfg, "intraday_1m_refresh_enabled", True)) and inapp_ok

    job_1d = reg["inapp_1d"]
    job_1d.schedule = f"Weekdays {refresh_time} IST"
    job_1d.universe = universe_1d
    job_1d.can_run = True
    if "inapp_1d" not in overrides:
        job_1d.enabled = inapp_ok
        if not inapp_ok:
            job_1d.last_status = "skipped"
            job_1d.last_detail = "Disabled or non-upstox source"
            job_1d.next_run_at = None

    job_1m = reg["inapp_1m"]
    job_1m.schedule = f"Mon–Fri 09:10–15:15 IST every {interval}s"
    job_1m.universe = f"{universe_1m} (limit {limit_1m})"
    job_1m.can_run = True
    if "inapp_1m" not in overrides:
        job_1m.enabled = one_m_enabled
        if not one_m_enabled:
            job_1m.last_status = "skipped"
            source = normalize_market_data_source(getattr(cfg, "market_data_source", "demo"))
            if not inapp_ok:
                job_1m.last_detail = f"Scheduler idle (source={source})"
            else:
                job_1m.last_detail = "INTRADAY_1M_REFRESH_ENABLED=false"
            job_1m.next_run_at = None

    for cron_id in ("cron_1m_today", "cron_1d", "cron_universe", "host_catchup", "host_1m_history"):
        reg[cron_id].can_run = cron_id in RUNNABLE_JOB_IDS
        if cron_id not in overrides:
            reg[cron_id].enabled = True

    hist = reg["host_1m_history"]
    hist.universe = universe_1d
    hist.schedule = "Manual — ~20–25 days 1m for RVOL lookback"

    _apply_overrides(app_state)
    return reg


def touch_job(
    app_state: Any,
    job_id: str,
    *,
    running: bool | None = None,
    status: str | None = None,
    detail: str | None = None,
    phase: str | None = None,
    next_run_at: datetime | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
    progress_done: int | None = None,
    progress_total: int | None = None,
    progress_current: str | None = None,
) -> SchedulerJobStatus:
    """Update one job row in the registry."""
    if job_id not in KNOWN_JOB_IDS:
        raise ValueError(f"Unknown scheduler job_id: {job_id}")
    reg = ensure_registry(app_state)
    job = reg[job_id]
    now = _utc_now()
    if mark_started:
        job.running = True
        job.last_started_at = now
        job.last_status = "running"
    if running is not None:
        job.running = running
    if status is not None:
        job.last_status = status
    if detail is not None:
        job.last_detail = detail
    if phase is not None:
        job.phase = phase
    if next_run_at is not None:
        job.next_run_at = next_run_at
    if progress_done is not None:
        job.progress_done = progress_done
    if progress_total is not None:
        job.progress_total = progress_total
    if progress_current is not None:
        job.progress_current = progress_current
    if job.progress_done is not None and job.progress_total:
        job.progress_pct = round(100.0 * job.progress_done / job.progress_total, 1)
    if mark_finished:
        job.running = False
        job.last_finished_at = now
        job.progress_current = None
        if job.last_status == "running":
            job.last_status = status or "ok"
    return job


def apply_heartbeat(
    app_state: Any,
    *,
    job_id: str,
    status: str,
    detail: str | None = None,
    phase: str | None = None,
    running: bool | None = None,
) -> SchedulerJobStatus:
    """Apply a host/cron heartbeat into the registry."""
    if job_id not in KNOWN_JOB_IDS:
        raise ValueError(f"Unknown scheduler job_id: {job_id}")
    is_running = running if running is not None else status == "running"
    if is_running:
        return touch_job(
            app_state,
            job_id,
            mark_started=True,
            status="running",
            detail=detail,
            phase=phase,
            running=True,
        )
    finished_status = status if status in ("ok", "failed", "skipped", "unknown") else "ok"
    return touch_job(
        app_state,
        job_id,
        mark_finished=True,
        status=finished_status,
        detail=detail,
        phase=phase,
        running=False,
    )


def snapshot_jobs(app_state: Any) -> list[dict[str, Any]]:
    """Ordered list of job dicts for the API."""
    reg = ensure_registry(app_state)
    _apply_overrides(app_state)
    return [reg[job_id].to_dict() for job_id in JOB_IDS if job_id in reg]


def compute_next_1d(settings: Settings | None = None) -> datetime | None:
    from zoneinfo import ZoneInfo

    from app.application.market_data.refresh_scheduler import (
        next_weekday_fire,
        parse_hhmm,
        scheduler_should_run,
    )

    cfg = settings or get_settings()
    if not scheduler_should_run(cfg):
        return None
    try:
        hour, minute = parse_hhmm(getattr(cfg, "market_data_refresh_time", "16:15"))
    except ValueError:
        return None
    ist = ZoneInfo("Asia/Kolkata")
    return next_weekday_fire(datetime.now(ist), hour, minute).astimezone(timezone.utc)


__all__ = [
    "JOB_IDS",
    "KNOWN_JOB_IDS",
    "RUNNABLE_JOB_IDS",
    "SchedulerJobStatus",
    "apply_heartbeat",
    "compute_next_1d",
    "ensure_registry",
    "is_job_enabled",
    "seed_registry_from_settings",
    "set_job_enabled",
    "snapshot_jobs",
    "touch_job",
]
