"""Unit tests for ScanRunRepository mapping (no PostgreSQL required)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.database.repositories.scan_run_repository import ScanRunRepository


@pytest.mark.asyncio
async def test_scan_run_repository_create_maps_domain():
    session = SimpleNamespace(add=lambda _row: None, flush=AsyncMock())
    repo = ScanRunRepository(session)
    started = datetime(2026, 9, 3, tzinfo=timezone.utc)
    finished = datetime(2026, 9, 3, 0, 0, 5, tzinfo=timezone.utc)

    # Inject id after add by mutating the ORM instance session.add receives
    captured = {}

    def _add(row):
        row.id = 42
        captured["row"] = row

    session.add = _add

    result = await repo.create(
        started_at=started,
        finished_at=finished,
        universe_date=finished,
        universe_version="v1",
        parameters={"timeframe": "1d"},
        result_count=109,
        metadata={"symbols_scanned": 498},
    )

    assert result.id == 42
    assert result.result_count == 109
    assert result.universe_version == "v1"
    assert result.parameters == {"timeframe": "1d"}
    assert result.metadata == {"symbols_scanned": 498}
    assert captured["row"].metadata_ == {"symbols_scanned": 498}
    session.flush.assert_awaited_once()
