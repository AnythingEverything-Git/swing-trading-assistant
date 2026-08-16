"""Domain `Instrument` type.

This module defines a minimal, framework-agnostic representation of a tradable
instrument used across the domain layer.
"""
from pydantic import BaseModel
from uuid import UUID
from typing import Optional, Dict, Any


class Instrument(BaseModel):
    id: UUID
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
