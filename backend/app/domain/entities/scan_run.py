"""Domain `ScanRun` type for auditability.

Contains metadata about a scan execution. Full ranked results may be stored in
`result_payload` for history replay; that payload is presentation JSON, not a second eligibility engine.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


SCAN_STATUS_QUEUED = "queued"
SCAN_STATUS_RUNNING = "running"
SCAN_STATUS_COMPLETED = "completed"
SCAN_STATUS_FAILED = "failed"


class ScanRun(BaseModel):
    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    universe_date: Optional[datetime] = None
    universe_version: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    result_count: int = 0
    metadata: Optional[Dict[str, Any]] = None
    result_payload: Optional[Dict[str, Any]] = None
    status: str = SCAN_STATUS_COMPLETED
    error_message: Optional[str] = None
