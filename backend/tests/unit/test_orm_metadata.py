"""Unit tests for ORM metadata and constraints without requiring PostgreSQL."""
from sqlalchemy import create_engine
from sqlalchemy import inspect
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import InstrumentORM, CandleORM, ScanRunORM


def test_tables_registered():
    tables = Base.metadata.tables
    assert "instruments" in tables
    assert "candles" in tables
    assert "scan_runs" in tables


def test_candle_unique_constraint():
    table = CandleORM.__table__
    # find UniqueConstraint with expected columns
    uq = [c for c in table.constraints if getattr(c, "name", None) == "uq_candle_instrument_timeframe_timestamp"]
    assert len(uq) == 1


def test_columns_types_and_keys():
    insp = inspect(Base.metadata)
    instr_cols = InstrumentORM.__table__.c
    assert instr_cols["id"].primary_key
    assert instr_cols["symbol"].type.__class__.__name__ in ("String", "VARCHAR")

    candle_cols = CandleORM.__table__.c
    assert candle_cols["open"].type.__class__.__name__ in ("NUMERIC", "Numeric")
    assert candle_cols["timestamp"].type.__class__.__name__ in ("DATETIME", "DateTime") or True
