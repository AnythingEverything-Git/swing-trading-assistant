"""Deterministic candle series that produces real Breakout->Retest->Confirmation setups.

Shared fixture data for tests and development/test seeding. Not a production
market-data source.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.market_data import Candle


def build_two_independent_setup_series() -> list[Candle]:
    """Deterministic series with two independent LONG Breakout->Retest->Confirmation setups.

    Setup 1 confirms at index 21 (entry 101.2). The next bar hits its 2R target so the
    first trade exits before setup 2. Setup 2 confirms at index 41 (entry 108.0).
    """
    levels = [
        (97.0, 97.5, 96.5, 96.8, 1200),
        (98.0, 98.9, 97.2, 97.6, 1200),
        (99.0, 99.8, 98.0, 98.4, 1200),
        (99.5, 100.0, 98.8, 99.3, 1200),
        (100.2, 100.6, 99.5, 99.9, 1200),
        (100.8, 101.5, 99.7, 100.6, 1300),
        (99.8, 100.3, 98.9, 99.2, 1300),
        (98.9, 99.2, 97.8, 98.5, 1300),
        (98.7, 99.0, 97.9, 98.2, 1200),
        (99.2, 99.6, 98.5, 98.9, 1200),
        (98.8, 99.3, 98.0, 98.5, 1200),
        (99.4, 99.9, 98.8, 99.1, 1200),
        (99.0, 99.4, 98.2, 98.6, 1200),
        (98.6, 98.9, 97.7, 98.3, 1200),
        (99.4, 99.8, 98.9, 99.1, 1200),
        (100.0, 100.3, 99.2, 99.6, 1400),
        (99.4, 99.8, 98.5, 98.9, 1300),
        (100.4, 101.0, 99.7, 100.2, 1300),
        (99.6, 100.0, 98.8, 99.2, 1300),
        (101.8, 102.2, 100.6, 101.1, 2000),
        (100.9, 101.0, 100.1, 100.5, 1500),
        (101.8, 102.2, 100.7, 101.2, 2200),
        (103.0, 107.5, 102.5, 107.0, 1800),
        (106.0, 106.5, 104.0, 104.5, 1400),
        (104.0, 104.5, 103.0, 103.5, 1400),
        (103.5, 104.0, 102.5, 103.0, 1400),
        (103.0, 105.0, 102.8, 104.5, 1500),
        (104.0, 104.8, 103.5, 104.0, 1400),
        (103.8, 104.2, 103.0, 103.5, 1400),
        (103.5, 104.0, 102.8, 103.2, 1400),
        (103.2, 103.8, 102.5, 103.0, 1400),
        (103.0, 103.5, 102.2, 102.8, 1400),
        (102.8, 103.2, 102.0, 102.5, 1400),
        (102.5, 103.0, 101.8, 102.2, 1400),
        (102.2, 102.8, 101.5, 102.0, 1400),
        (102.0, 104.5, 101.8, 104.0, 1500),
        (104.0, 106.0, 103.5, 105.0, 1600),
        (104.5, 105.2, 103.8, 104.2, 1500),
        (104.0, 104.8, 103.5, 104.0, 1500),
        (105.5, 108.0, 105.0, 107.5, 3000),
        (106.5, 107.0, 105.8, 106.2, 2000),
        (107.0, 108.5, 106.5, 108.0, 2800),
        (108.0, 115.0, 107.5, 114.0, 2500),
    ]
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            symbol="TST",
            exchange="TEST",
            instrument_id=1,
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            open=Decimal(str(open_)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=volume,
        )
        for index, (open_, high, low, close, volume) in enumerate(levels)
    ]


__all__ = ["build_two_independent_setup_series"]
