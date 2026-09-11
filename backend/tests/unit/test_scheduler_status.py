"""Unit tests for ops scheduler registry + heartbeat helpers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.application.ops.scheduler_status import (
    apply_heartbeat,
    ensure_registry,
    is_job_enabled,
    seed_registry_from_settings,
    set_job_enabled,
    snapshot_jobs,
    touch_job,
)
from app.core.config import Settings


def test_ensure_registry_seeds_known_jobs():
    state = SimpleNamespace()
    reg = ensure_registry(state)
    assert "inapp_1d" in reg
    assert "cron_1m_today" in reg
    assert "host_catchup" in reg
    jobs = snapshot_jobs(state)
    assert [j["job_id"] for j in jobs] == [
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
    ]


def test_touch_job_marks_running_and_finished():
    state = SimpleNamespace()
    ensure_registry(state)
    touch_job(state, "inapp_1d", mark_started=True)
    assert state.scheduler_registry["inapp_1d"].running is True
    assert state.scheduler_registry["inapp_1d"].last_status == "running"
    touch_job(
        state,
        "inapp_1d",
        mark_finished=True,
        status="ok",
        detail="attempted=10 success=10",
    )
    job = state.scheduler_registry["inapp_1d"]
    assert job.running is False
    assert job.last_status == "ok"
    assert "attempted=10" in (job.last_detail or "")
    assert job.last_finished_at is not None


def test_apply_heartbeat_running_and_ok():
    state = SimpleNamespace()
    ensure_registry(state)
    apply_heartbeat(state, job_id="cron_1d", status="running", detail="start")
    assert state.scheduler_registry["cron_1d"].running is True
    apply_heartbeat(state, job_id="cron_1d", status="ok", detail="done")
    job = state.scheduler_registry["cron_1d"]
    assert job.running is False
    assert job.last_status == "ok"
    assert job.last_detail == "done"


def test_apply_heartbeat_unknown_job():
    state = SimpleNamespace()
    ensure_registry(state)
    with pytest.raises(ValueError):
        apply_heartbeat(state, job_id="nope", status="ok")


def test_seed_registry_disables_inapp_for_demo():
    state = SimpleNamespace()
    settings = Settings(
        environment="development",
        market_data_source="demo",
        database_url="postgresql+psycopg://x:y@localhost/z",
        _env_file=None,
    )
    seed_registry_from_settings(state, settings)
    assert state.scheduler_registry["inapp_1d"].enabled is False
    assert state.scheduler_registry["inapp_1m"].enabled is False


def test_set_job_enabled_override_persists_across_seed():
    state = SimpleNamespace()
    settings = Settings(
        environment="development",
        market_data_source="demo",
        database_url="postgresql+psycopg://x:y@localhost/z",
        _env_file=None,
    )
    seed_registry_from_settings(state, settings)
    set_job_enabled(state, "inapp_1m", True)
    assert is_job_enabled(state, "inapp_1m") is True
    seed_registry_from_settings(state, settings)
    assert is_job_enabled(state, "inapp_1m") is True
    set_job_enabled(state, "inapp_1m", False)
    assert is_job_enabled(state, "inapp_1m") is False
