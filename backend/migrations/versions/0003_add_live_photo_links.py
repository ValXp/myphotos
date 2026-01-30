"""Add live photo links.

Revision ID: 0003_add_live_photo_links
Revises: 0002_add_asset_identity_columns
Create Date: 2026-01-30 00:35:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_add_live_photo_links"
down_revision = "0002_add_asset_identity_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("live_photo_video_id", sa.String(length=36)))
    op.create_foreign_key(
        "fk_assets_live_photo_video_id",
        "assets",
        "assets",
        ["live_photo_video_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_assets_live_photo_video_id",
        "assets",
        ["live_photo_video_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_assets_live_photo_video_id", "assets", type_="unique")
    op.drop_constraint(
        "fk_assets_live_photo_video_id",
        "assets",
        type_="foreignkey",
    )
    op.drop_column("assets", "live_photo_video_id")
