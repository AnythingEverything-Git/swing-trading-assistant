"""Domain `Candle` (OHLCV) type.

Daily OHLCV candles are used by the initial strategy.
"""
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Literal


class Candle(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timeframe: Literal["1d"] = "1d"
