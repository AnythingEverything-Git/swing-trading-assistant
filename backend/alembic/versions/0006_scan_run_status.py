"""Add status and error_message to scan_runs for async jobs.

Revision ID: 0006_scan_run_status
Revises: 0005_paper_trades
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_scan_run_status"
down_revision = "0005_paper_trades"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scan_runs",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="completed"),
    )
    op.add_column(
        "scan_runs",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"])


def downgrade():
    op.drop_index("ix_scan_runs_status", table_name="scan_runs")
    op.drop_column("scan_runs", "error_message")
    op.drop_column("scan_runs", "status")
