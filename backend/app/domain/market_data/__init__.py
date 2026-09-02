"""Domain market data abstractions.

This module defines the canonical market-data `Candle` domain type used by
providers and strategy logic. It is intentionally a lightweight frozen dataclass
with Decimal-based OHLC values and no layer-specific trading logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Union


def _as_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a valid Decimal value")
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"{field_name} must be a valid Decimal value") from exc
    else:
        raise TypeError(f"{field_name} must be Decimal, int, or str")

    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError(f"{field_name} must be a positive finite Decimal")
    return decimal_value


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

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not self.exchange or not self.exchange.strip():
            raise ValueError("exchange must be a non-empty string")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if self.volume is not None and (not isinstance(self.volume, int) or isinstance(self.volume, bool) or self.volume < 0):
            raise ValueError("volume must be a non-negative integer or None")

        object.__setattr__(self, "open", _as_decimal(self.open, "open"))
        object.__setattr__(self, "high", _as_decimal(self.high, "high"))
        object.__setattr__(self, "low", _as_decimal(self.low, "low"))
        object.__setattr__(self, "close", _as_decimal(self.close, "close"))


__all__ = ["Candle"]
