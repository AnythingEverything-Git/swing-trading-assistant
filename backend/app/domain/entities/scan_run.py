"""Domain `ScanRun` type for auditability.

Contains metadata about a scan execution; the full instrument list is not stored
inside ScanRun (per architecture rules).
"""
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any


class ScanRun(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: Optional[datetime] = None
    universe_date: Optional[datetime] = None
    universe_version: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    result_count: int = 0
    metadata: Optional[Dict[str, Any]] = None
