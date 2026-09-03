"""Widen candle volume to bigint for high-volume NSE names.

Revision ID: 0004_candle_volume_bigint
Revises: 0003_scan_run_payload
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_candle_volume_bigint"
down_revision = "0003_scan_run_payload"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "candles",
        "volume",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "candles",
        "volume",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
