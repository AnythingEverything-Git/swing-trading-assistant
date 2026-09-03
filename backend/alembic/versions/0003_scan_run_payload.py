"""Add result_payload JSON to scan_runs for history replay.

Revision ID: 0003_scan_run_payload
Revises: 0002_scan_runs
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_scan_run_payload"
down_revision = "0002_scan_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("scan_runs", sa.Column("result_payload", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("scan_runs", "result_payload")
