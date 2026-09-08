"""Alembic: intraday ORB practice trades (no profit target).

Revision ID: 0008_intraday_practice
Revises: 0007_intraday_sessions
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_intraday_practice"
down_revision = "0007_intraday_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "intraday_practice_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("stop_loss", sa.Numeric(18, 6), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("risk_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("exit_reason", sa.String(length=32), nullable=True),
        sa.Column("last_mark_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(18, 6), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(18, 6), nullable=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intraday_practice_trades_session_id", "intraday_practice_trades", ["session_id"])
    op.create_index("ix_intraday_practice_trades_session_date", "intraday_practice_trades", ["session_date"])
    op.create_index("ix_intraday_practice_trades_symbol", "intraday_practice_trades", ["symbol"])
    op.create_index("ix_intraday_practice_trades_status", "intraday_practice_trades", ["status"])


def downgrade():
    op.drop_index("ix_intraday_practice_trades_status", table_name="intraday_practice_trades")
    op.drop_index("ix_intraday_practice_trades_symbol", table_name="intraday_practice_trades")
    op.drop_index("ix_intraday_practice_trades_session_date", table_name="intraday_practice_trades")
    op.drop_index("ix_intraday_practice_trades_session_id", table_name="intraday_practice_trades")
    op.drop_table("intraday_practice_trades")
