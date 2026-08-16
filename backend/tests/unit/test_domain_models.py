"""Unit tests to ensure domain types can be instantiated."""
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.entities.instrument import Instrument
from app.domain.entities.candle import Candle
from app.domain.entities.scan_run import ScanRun


def test_instrument_instantiation():
    inst = Instrument(id=uuid4(), symbol="ABC", name="ABC Ltd", exchange="NSE")
    assert inst.symbol == "ABC"


def test_candle_instantiation():
    c = Candle(timestamp=datetime.now(timezone.utc), open=Decimal("100.0"), high=Decimal("110.0"), low=Decimal("95.0"), close=Decimal("105.0"), volume=1000)
    assert c.timeframe == "1d"


def test_scanrun_instantiation():
    sr = ScanRun(id=uuid4(), started_at=datetime.now(timezone.utc), result_count=0)
    assert sr.result_count == 0
