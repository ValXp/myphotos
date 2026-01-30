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
    start: datetime | None = None,
    end: datetime | None = None,
    min_lat: float | None = None,
    min_lon: float | None = None,
    max_lat: float | None = None,
    max_lon: float | None = None,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    sort_ts = func.coalesce(Asset.captured_at, Asset.created_at)
    query = db.query(Asset, sort_ts.label("sort_ts")).order_by(
        sort_ts.desc(), Asset.id.desc()
    )
    start_dt = _normalize_datetime(start)
    end_dt = _normalize_datetime(end)
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="invalid date range")
    if start_dt or end_dt:
        captured_filters = []
        created_filters = [Asset.captured_at.is_(None)]
        if start_dt:
            captured_filters.append(Asset.captured_at >= start_dt)
            created_filters.append(Asset.created_at >= start_dt)
        if end_dt:
            captured_filters.append(Asset.captured_at <= end_dt)
            created_filters.append(Asset.created_at <= end_dt)
        query = query.filter(
            or_(
                and_(*captured_filters),
                and_(*created_filters),
            )
        )
    bbox_values = [min_lat, min_lon, max_lat, max_lon]
    if any(value is not None for value in bbox_values):
        if any(value is None for value in bbox_values):
            raise HTTPException(status_code=400, detail="bbox requires all bounds")
        if min_lat > max_lat or min_lon > max_lon:
            raise HTTPException(status_code=400, detail="invalid bbox bounds")
        query = query.filter(
            Asset.lat.isnot(None),
            Asset.lon.isnot(None),
            Asset.lat >= min_lat,
            Asset.lat <= max_lat,
            Asset.lon >= min_lon,
            Asset.lon <= max_lon,
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


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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
