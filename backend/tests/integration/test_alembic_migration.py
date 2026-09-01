import os
import tempfile

from sqlalchemy import create_engine, inspect
from alembic.config import Config
from alembic import command


def test_alembic_upgrade_creates_tables(tmp_path):
    db_path = tmp_path / "mig.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url

    # run alembic upgrade head
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    command.upgrade(cfg, "head")

    # inspect DB
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "instruments" in tables
    assert "candles" in tables

    # Check columns on instruments
    cols = {c['name']: c for c in inspector.get_columns('instruments')}
    assert 'id' in cols
    assert 'symbol' in cols
    assert 'metadata' in cols

    # Check columns on candles
    ccols = {c['name']: c for c in inspector.get_columns('candles')}
    assert 'instrument_id' in ccols
    assert 'timestamp' in ccols
    assert 'open' in ccols

    # Check unique constraint exists on candles (instrument_id + timeframe + timestamp)
    uniques = inspector.get_unique_constraints('candles')
    found = False
    for u in uniques:
        if set(u.get('column_names') or u.get('column_names', [])) == {'instrument_id', 'timeframe', 'timestamp'}:
            found = True
    assert found, f"Unique constraints found: {uniques}"
