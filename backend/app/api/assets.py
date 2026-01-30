from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_owner_session
from app.auth.sessions import Session as OwnerSession
from app.db.models import Asset


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200

router = APIRouter()


@router.get("/assets")
def list_assets(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    sort_ts = func.coalesce(Asset.captured_at, Asset.created_at)
    query = db.query(Asset, sort_ts.label("sort_ts")).order_by(
        sort_ts.desc(), Asset.id.desc()
    )
    if cursor:
        try:
            cursor_ts, cursor_id = _decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
        query = query.filter(
            or_(
                sort_ts < cursor_ts,
                and_(sort_ts == cursor_ts, Asset.id < cursor_id),
            )
        )
    rows = query.limit(limit + 1).all()
    items = []
    for asset, _ in rows[:limit]:
        items.append(_serialize_asset_summary(asset))
    next_cursor = None
    if len(rows) > limit:
        last_asset, last_sort_ts = rows[limit - 1]
        next_cursor = _encode_cursor(last_sort_ts, last_asset.id)
    return {"items": items, "next_cursor": next_cursor}


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


def _encode_cursor(sort_ts: datetime, asset_id: str) -> str:
    if sort_ts.tzinfo is None:
        sort_ts = sort_ts.replace(tzinfo=timezone.utc)
    ms = int(sort_ts.timestamp() * 1000)
    payload = f"{ms}:{asset_id}".encode("ascii")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    if not cursor.strip():
        raise ValueError("cursor must be non-empty")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("cursor decode failed") from exc
    parts = raw.split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        raise ValueError("cursor format invalid")
    timestamp_ms = int(parts[0])
    asset_id = parts[1]
    if not asset_id:
        raise ValueError("cursor asset id missing")
    sort_ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return sort_ts, asset_id
