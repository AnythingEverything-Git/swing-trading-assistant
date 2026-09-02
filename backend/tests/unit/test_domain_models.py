"""Unit tests to ensure domain types can be instantiated."""
from dataclasses import FrozenInstanceError
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.entities.instrument import Instrument
from app.domain.entities.candle import Candle
from app.domain.entities.scan_run import ScanRun


def test_instrument_instantiation():
    inst = Instrument(id=uuid4(), symbol="ABC", name="ABC Ltd", exchange="NSE")
    assert inst.symbol == "ABC"


def test_candle_instantiation():
    c = Candle(
        symbol="ABC",
        exchange="NSE",
        instrument_id=1,
        timeframe="1d",
        timestamp=datetime.now(timezone.utc),
        open=Decimal("100.0"),
        high=Decimal("110.0"),
        low=Decimal("95.0"),
        close=Decimal("105.0"),
        volume=1000,
    )
    assert c.timeframe == "1d"
    assert isinstance(c.open, Decimal)
    assert isinstance(c.high, Decimal)
    assert isinstance(c.low, Decimal)
    assert isinstance(c.close, Decimal)


def test_candle_is_immutable_and_rejects_invalid_prices():
    c = Candle(
        symbol="ABC",
        exchange="NSE",
        instrument_id=1,
        timeframe="1d",
        timestamp=datetime.now(timezone.utc),
        open=Decimal("100.0"),
        high=Decimal("110.0"),
        low=Decimal("95.0"),
        close=Decimal("105.0"),
        volume=1000,
    )

    assert isinstance(c.open, Decimal)
    with pytest.raises(FrozenInstanceError):
        c.close = Decimal("110.0")

    with pytest.raises(ValueError):
        Candle(
            symbol="ABC",
            exchange="NSE",
            instrument_id=1,
            timeframe="1d",
            timestamp=datetime.now(timezone.utc),
            open=Decimal("0"),
            high=Decimal("110.0"),
            low=Decimal("95.0"),
            close=Decimal("105.0"),
            volume=1000,
        )


def test_scanrun_instantiation():
    sr = ScanRun(id=uuid4(), started_at=datetime.now(timezone.utc), result_count=0)
    assert sr.result_count == 0
