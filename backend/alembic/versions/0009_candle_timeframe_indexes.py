"""Add candle timeframe indexes for status/board SLA queries.

Revision ID: 0009_candle_timeframe_indexes
Revises: 0008_intraday_practice
Create Date: 2026-09-12
"""
from alembic import op

revision = "0009_candle_timeframe_indexes"
down_revision = "0008_intraday_practice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_candles_timeframe_timestamp",
        "candles",
        ["timeframe", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_candles_timeframe_instrument",
        "candles",
        ["timeframe", "instrument_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_candles_timeframe_instrument", table_name="candles")
    op.drop_index("ix_candles_timeframe_timestamp", table_name="candles")
