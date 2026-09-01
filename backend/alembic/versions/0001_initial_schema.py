"""Initial schema for instruments and candles.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Instruments table
    op.create_table(
        'instruments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('exchange', sa.String(length=50), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.UniqueConstraint('symbol', name='uq_instruments_symbol'),
    )
    op.create_index('ix_instruments_symbol', 'instruments', ['symbol'])

    # Candles table
    op.create_table(
        'candles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('instrument_id', sa.Integer(), sa.ForeignKey('instruments.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False, server_default='1d'),
        sa.Column('open', sa.Numeric(18, 8), nullable=False),
        sa.Column('high', sa.Numeric(18, 8), nullable=False),
        sa.Column('low', sa.Numeric(18, 8), nullable=False),
        sa.Column('close', sa.Numeric(18, 8), nullable=False),
        sa.Column('volume', sa.Integer(), nullable=True),
        sa.UniqueConstraint('instrument_id', 'timeframe', 'timestamp', name='uq_candle_instrument_timeframe_timestamp'),
    )
    op.create_index('ix_candles_instrument_id', 'candles', ['instrument_id'])


def downgrade():
    op.drop_index('ix_candles_instrument_id', table_name='candles')
    op.drop_table('candles')

    op.drop_index('ix_instruments_symbol', table_name='instruments')
    op.drop_table('instruments')
