"""Domain market data abstractions.

This module defines a simple, infrastructure-agnostic `Candle` domain
type used by market-data providers. The type is intentionally a
lightweight frozen dataclass to keep the domain layer dependency-free
and easy to construct in tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Union


@dataclass(frozen=True)
class Candle:
	symbol: str
	exchange: str
	instrument_id: Optional[Union[str, int]]
	timeframe: str
	timestamp: datetime
	open: Decimal
	high: Decimal
	low: Decimal
	close: Decimal
	volume: Optional[int]

__all__ = ["Candle"]
