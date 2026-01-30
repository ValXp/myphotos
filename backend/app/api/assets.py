from __future__ import annotations

import base64
import binascii
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_config, get_db, require_owner_session
from app.auth.sessions import Session as OwnerSession
from app.config import Config
from app.db.enums import AssetType, AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.media.transcode import master_manifest_path


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200
THUMB_CACHE_CONTROL = "public, max-age=31536000, immutable"
ORIGINAL_CACHE_CONTROL = "private, max-age=86400"
STREAM_CACHE_CONTROL = "private, max-age=60"
LIVE_CACHE_CONTROL = "private, max-age=60"
RANGE_CHUNK_SIZE = 1024 * 1024
STREAM_MEDIA_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/MP2T",
}

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


@router.get("/assets/{asset_id}")
def get_asset_detail(
    asset_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    asset = (
        db.query(Asset)
        .options(selectinload(Asset.variants))
        .filter(Asset.id == asset_id)
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return _serialize_asset_detail(asset)


@router.get("/assets/{asset_id}/thumb")
def get_asset_thumbnail(
    asset_id: str,
    request: Request,
    profile: str | None = None,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    _: OwnerSession = Depends(require_owner_session),
) -> Response:
    asset = (
        db.query(Asset)
        .options(selectinload(Asset.variants))
        .filter(Asset.id == asset_id)
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    variant = _select_thumbnail_variant(asset.variants, profile)
    if variant is None:
        raise HTTPException(status_code=404, detail="thumbnail not found")
    path = _resolve_variant_path(variant.path, config.paths.derived)
    media_type = _guess_media_type(path, default="image/jpeg")
    return _build_file_response(
        path,
        request,
        media_type=media_type,
        cache_control=THUMB_CACHE_CONTROL,
        enable_range=False,
        missing_detail="thumbnail not found",
    )


@router.get("/assets/{asset_id}/original")
def get_asset_original(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    _: OwnerSession = Depends(require_owner_session),
) -> Response:
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    path = _resolve_original_path(asset.original_path, config.paths.originals)
    return _build_file_response(
        path,
        request,
        media_type=asset.original_mime,
        cache_control=ORIGINAL_CACHE_CONTROL,
        enable_range=True,
        missing_detail="original not found",
    )


@router.get("/assets/{asset_id}/stream")
def get_asset_stream(
    asset_id: str,
    request: Request,
    file: str | None = None,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    _: OwnerSession = Depends(require_owner_session),
) -> Response:
    asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset.type not in {AssetType.video, AssetType.live_photo}:
        raise HTTPException(status_code=404, detail="stream not found")
    stream_path = _resolve_stream_path(asset_id, config.paths.derived, file)
    media_type = _stream_media_type(stream_path)
    return _build_file_response(
        stream_path,
        request,
        media_type=media_type,
        cache_control=STREAM_CACHE_CONTROL,
        enable_range=True,
        missing_detail="stream not found",
    )


@router.get("/assets/{asset_id}/live")
def get_asset_live_video(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    _: OwnerSession = Depends(require_owner_session),
) -> Response:
    asset = (
        db.query(Asset)
        .options(selectinload(Asset.variants))
        .filter(Asset.id == asset_id)
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset.type != AssetType.live_photo:
        raise HTTPException(status_code=404, detail="live video not found")
    variant = _select_live_video_variant(asset.variants)
    if variant is None:
        raise HTTPException(status_code=404, detail="live video not found")
    path = _resolve_variant_path(variant.path, config.paths.derived)
    media_type = _guess_media_type(path, default="video/mp4")
    return _build_file_response(
        path,
        request,
        media_type=media_type,
        cache_control=LIVE_CACHE_CONTROL,
        enable_range=True,
        missing_detail="live video not found",
    )


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


def _serialize_asset_detail(asset: Asset) -> dict[str, object]:
    variants = sorted(asset.variants, key=_variant_sort_key)
    return {
        "id": asset.id,
        "type": asset.type,
        "created_at": _isoformat(asset.created_at),
        "captured_at": _isoformat(asset.captured_at),
        "duration_ms": asset.duration_ms,
        "width": asset.width,
        "height": asset.height,
        "lat": asset.lat,
        "lon": asset.lon,
        "hash": asset.hash,
        "original_path": asset.original_path,
        "original_bytes": asset.original_bytes,
        "original_mime": asset.original_mime,
        "live_photo_video_id": asset.live_photo_video_id,
        "variants": [_serialize_variant(variant) for variant in variants],
    }


def _serialize_variant(variant: AssetVariant) -> dict[str, object]:
    return {
        "id": variant.id,
        "kind": variant.kind,
        "profile": variant.profile,
        "path": variant.path,
        "bytes": variant.bytes,
        "created_at": _isoformat(variant.created_at),
    }


def _variant_sort_key(variant: AssetVariant) -> tuple[str, str, str]:
    kind = variant.kind.value if variant.kind else ""
    return (kind, variant.profile, variant.id)


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


def _select_thumbnail_variant(
    variants: list[AssetVariant], profile: str | None
) -> AssetVariant | None:
    thumb_variants = [variant for variant in variants if variant.kind == AssetVariantKind.thumb]
    if not thumb_variants:
        return None
    if profile:
        for variant in thumb_variants:
            if variant.profile == profile:
                return variant
        return None
    preferred = ("thumb_md", "thumb_sm", "thumb_lg", "poster")
    for name in preferred:
        for variant in thumb_variants:
            if variant.profile == name:
                return variant
    return thumb_variants[0]


def _select_live_video_variant(variants: list[AssetVariant]) -> AssetVariant | None:
    for variant in variants:
        if variant.kind == AssetVariantKind.live_video:
            return variant
    return None


def _resolve_stream_path(asset_id: str, derived_root: Path, filename: str | None) -> Path:
    if filename is None or not filename.strip():
        return master_manifest_path(derived_root, asset_id)
    normalized = filename.strip()
    if "/" in normalized or "\\" in normalized:
        raise HTTPException(status_code=400, detail="invalid stream file")
    if normalized.startswith(".") or ".." in normalized:
        raise HTTPException(status_code=400, detail="invalid stream file")
    path = derived_root / asset_id / AssetVariantKind.video_transcode.value / normalized
    if path.suffix.lower() not in STREAM_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail="unsupported stream file")
    return path


def _stream_media_type(path: Path) -> str:
    return STREAM_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _resolve_variant_path(path: str, derived_root: Path) -> Path:
    variant_path = Path(path)
    if variant_path.is_absolute():
        return variant_path
    return derived_root / variant_path


def _resolve_original_path(path: str, originals_root: Path) -> Path:
    original_path = Path(path)
    if original_path.is_absolute():
        return original_path
    return originals_root / original_path


def _guess_media_type(path: Path, default: str) -> str:
    guess, _ = mimetypes.guess_type(path.name, strict=False)
    return guess or default


def _build_file_response(
    path: Path,
    request: Request,
    *,
    media_type: str,
    cache_control: str,
    enable_range: bool,
    missing_detail: str,
) -> Response:
    try:
        stat_result = path.stat()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=missing_detail) from exc

    headers = {
        "Cache-Control": cache_control,
        "Accept-Ranges": "bytes",
    }
    range_header = request.headers.get("range")
    if enable_range and range_header:
        try:
            start, end = _parse_range_header(range_header, stat_result.st_size)
        except ValueError:
            headers["Content-Range"] = f"bytes */{stat_result.st_size}"
            return Response(status_code=416, headers=headers)
        length = end - start + 1
        headers["Content-Range"] = f"bytes {start}-{end}/{stat_result.st_size}"
        headers["Content-Length"] = str(length)
        return StreamingResponse(
            _iter_file_range(path, start, length),
            status_code=206,
            headers=headers,
            media_type=media_type,
        )
    return FileResponse(path, media_type=media_type, headers=headers)


def _parse_range_header(range_header: str, size: int) -> tuple[int, int]:
    if size <= 0:
        raise ValueError("invalid size")
    header = range_header.strip()
    if not header.lower().startswith("bytes="):
        raise ValueError("unsupported range unit")
    range_spec = header.split("=", 1)[1].strip()
    if "," in range_spec:
        raise ValueError("multiple ranges not supported")
    if "-" not in range_spec:
        raise ValueError("invalid range")
    start_str, end_str = range_spec.split("-", 1)
    if not start_str:
        if not end_str:
            raise ValueError("invalid suffix range")
        suffix = int(end_str)
        if suffix <= 0:
            raise ValueError("invalid suffix length")
        if suffix > size:
            suffix = size
        start = size - suffix
        end = size - 1
    else:
        start = int(start_str)
        if start < 0:
            raise ValueError("invalid start")
        if end_str:
            end = int(end_str)
        else:
            end = size - 1
        if start > end:
            raise ValueError("invalid range order")
    if start >= size:
        raise ValueError("range start beyond size")
    if end >= size:
        end = size - 1
    return start, end


def _iter_file_range(path: Path, start: int, length: int):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(RANGE_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
