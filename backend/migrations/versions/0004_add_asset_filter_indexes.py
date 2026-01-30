"""Add asset filter indexes.

Revision ID: 0004_add_asset_filter_indexes
Revises: 0003_add_live_photo_links
Create Date: 2026-01-30 02:10:00
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_add_asset_filter_indexes"
down_revision = "0003_add_live_photo_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_assets_captured_at", "assets", ["captured_at"])
    op.create_index("ix_assets_created_at", "assets", ["created_at"])
    op.create_index("ix_assets_lat_lon", "assets", ["lat", "lon"])


def downgrade() -> None:
    op.drop_index("ix_assets_lat_lon", table_name="assets")
    op.drop_index("ix_assets_created_at", table_name="assets")
    op.drop_index("ix_assets_captured_at", table_name="assets")
