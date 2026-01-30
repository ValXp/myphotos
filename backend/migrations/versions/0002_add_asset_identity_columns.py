"""Add asset identity columns.

Revision ID: 0002_add_asset_identity_columns
Revises: 0001_create_core_tables
Create Date: 2026-01-30 00:25:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_asset_identity_columns"
down_revision = "0001_create_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("original_device", sa.BigInteger()))
    op.add_column("assets", sa.Column("original_inode", sa.BigInteger()))
    op.add_column("assets", sa.Column("original_mtime_ns", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("assets", "original_mtime_ns")
    op.drop_column("assets", "original_inode")
    op.drop_column("assets", "original_device")
