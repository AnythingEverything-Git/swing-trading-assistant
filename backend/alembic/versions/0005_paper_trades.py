"""Create paper_trades table for simulated agent fills.

Revision ID: 0005_paper_trades
Revises: 0004_candle_volume_bigint
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_paper_trades"
down_revision = "0004_candle_volume_bigint"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_run_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("stop_loss", sa.Numeric(18, 6), nullable=False),
        sa.Column("target", sa.Numeric(18, 6), nullable=False),
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
        sa.Column("setup_name", sa.String(length=128), nullable=True),
        sa.Column("quality_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_trades_scan_run_id", "paper_trades", ["scan_run_id"])
    op.create_index("ix_paper_trades_symbol", "paper_trades", ["symbol"])
    op.create_index("ix_paper_trades_status", "paper_trades", ["status"])


def downgrade():
    op.drop_index("ix_paper_trades_status", table_name="paper_trades")
    op.drop_index("ix_paper_trades_symbol", table_name="paper_trades")
    op.drop_index("ix_paper_trades_scan_run_id", table_name="paper_trades")
    op.drop_table("paper_trades")
