from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import require_share_link
from app.db.models import ShareLink


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


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
