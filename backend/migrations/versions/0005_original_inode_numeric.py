"""Use NUMERIC for original inode.

Revision ID: 0005_original_inode_numeric
Revises: 0004_add_asset_filter_indexes
Create Date: 2026-01-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_original_inode_numeric"
down_revision = "0004_add_asset_filter_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "assets",
        "original_inode",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(20, 0, asdecimal=False),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "original_inode",
        existing_type=sa.Numeric(20, 0, asdecimal=False),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
