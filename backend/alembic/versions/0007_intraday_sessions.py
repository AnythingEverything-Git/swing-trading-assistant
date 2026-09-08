"""Create intraday_sessions table for ORB session audit.

Revision ID: 0007_intraday_sessions
Revises: 0006_scan_run_status
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_intraday_sessions"
down_revision = "0006_scan_run_status"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "intraday_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=32), nullable=False),
        sa.Column("data_source", sa.String(length=16), nullable=False),
        sa.Column("equity", sa.Numeric(18, 2), nullable=True),
        sa.Column("coverage_eligible", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fill_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(18, 6), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intraday_sessions_session_date", "intraday_sessions", ["session_date"])
    op.create_index("ix_intraday_sessions_created_at", "intraday_sessions", ["created_at"])
    op.create_index("ix_intraday_sessions_data_source", "intraday_sessions", ["data_source"])


def downgrade():
    op.drop_index("ix_intraday_sessions_data_source", table_name="intraday_sessions")
    op.drop_index("ix_intraday_sessions_created_at", table_name="intraday_sessions")
    op.drop_index("ix_intraday_sessions_session_date", table_name="intraday_sessions")
    op.drop_table("intraday_sessions")
