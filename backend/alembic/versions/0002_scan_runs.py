"""Add scan_runs audit table.

Revision ID: 0002_scan_runs
Revises: 0001_initial_schema
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_scan_runs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("universe_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("universe_version", sa.String(length=128), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_table("scan_runs")
