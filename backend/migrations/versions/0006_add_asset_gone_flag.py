"""Add gone flag to assets.

Revision ID: 0006_add_asset_gone_flag
Revises: 0005_original_inode_numeric
Create Date: 2026-01-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_add_asset_gone_flag"
down_revision = "0005_original_inode_numeric"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("gone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "assets",
        sa.Column("gone_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assets_gone", "assets", ["gone"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assets_gone", table_name="assets")
    op.drop_column("assets", "gone_at")
    op.drop_column("assets", "gone")
