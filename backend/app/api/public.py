from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_share_link
from app.db.models import AlbumItem, Asset, ShareLink


router = APIRouter(prefix="/public/shares")


@router.get("/{token}/album")
def get_public_album(
    share: ShareLink = Depends(require_share_link),
) -> dict[str, object]:
    album = share.album
    return {
        "id": album.id,
        "title": album.title,
        "created_at": _isoformat(album.created_at),
        "updated_at": _isoformat(album.updated_at),
    }


@router.get("/{token}/assets")
def list_public_album_assets(
    share: ShareLink = Depends(require_share_link),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rows = (
        db.query(AlbumItem, Asset)
        .join(Asset, AlbumItem.asset_id == Asset.id)
        .filter(AlbumItem.album_id == share.album_id)
        .order_by(AlbumItem.order_index.asc(), AlbumItem.asset_id.asc())
        .all()
    )
    items = [_serialize_asset_summary(asset) for _, asset in rows]
    return {"items": items}


def _serialize_asset_summary(asset: Asset) -> dict[str, object]:
    return {
        "id": asset.id,
        "type": asset.type,
        "captured_at": _isoformat(asset.captured_at),
        "created_at": _isoformat(asset.created_at),
        "duration_ms": asset.duration_ms,
        "width": asset.width,
        "height": asset.height,
        "live_photo_video_id": asset.live_photo_video_id,
    }


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
