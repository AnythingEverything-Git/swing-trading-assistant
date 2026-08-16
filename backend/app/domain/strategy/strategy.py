"""Strategy protocol abstraction.

Defines the `Strategy` protocol and `StrategyResult` type used by the
application layer. Implementations will be added later.
"""
from typing import Protocol, List, Dict, Any
from ..entities.instrument import Instrument
from ..entities.candle import Candle
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class StrategyResult(BaseModel):
    instrument_id: UUID
    timestamp: datetime
    score: float
    signals: Dict[str, Any]
    notes: Dict[str, Any]


class Strategy(Protocol):
    def analyze(self, instrument: Instrument, candles: List[Candle]) -> StrategyResult:  # pragma: no cover - interface
        """Analyze the given instrument and candles, returning a deterministic result."""
