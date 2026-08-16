"""Pydantic schemas for API request/response shapes.

Note: these mirror domain types but are API-layer DTOs. No business logic here.
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class HealthCheck(BaseModel):
    status: str


class InstrumentSchema(BaseModel):
    id: UUID
    symbol: str
    name: Optional[str]
    exchange: Optional[str]


class CandleSchema(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class ScanRunSchema(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: Optional[datetime]
    universe_date: Optional[datetime]
    universe_version: Optional[str]
    parameters: Optional[Dict[str, Any]]
    result_count: int
    metadata: Optional[Dict[str, Any]]
