from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.api.assets import (
    STREAM_CACHE_CONTROL,
    THUMB_CACHE_CONTROL,
    _build_file_response,
    _guess_media_type,
    _resolve_stream_path,
    _resolve_variant_path,
    _select_thumbnail_variant,
    _stream_media_type,
)
from app.api.deps import get_config, get_db, require_share_link
from app.config import Config
from app.db.enums import AssetType
from app.db.models import AlbumItem, Asset, ShareLink
from app.downloads.zip_jobs import album_zip_path, album_zip_ready, album_zip_record


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


@router.get("/{token}/assets/{asset_id}/thumb")
def get_public_asset_thumbnail(
    asset_id: str,
    request: Request,
    profile: str | None = None,
    share: ShareLink = Depends(require_share_link),
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
) -> Response:
    asset = (
        db.query(Asset)
        .options(selectinload(Asset.variants))
        .join(AlbumItem, AlbumItem.asset_id == Asset.id)
        .filter(AlbumItem.album_id == share.album_id, Asset.id == asset_id)
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


@router.get("/{token}/assets/{asset_id}/stream")
def get_public_asset_stream(
    asset_id: str,
    request: Request,
    file: str | None = None,
    share: ShareLink = Depends(require_share_link),
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
) -> Response:
    asset = (
        db.query(Asset)
        .join(AlbumItem, AlbumItem.asset_id == Asset.id)
        .filter(AlbumItem.album_id == share.album_id, Asset.id == asset_id)
        .one_or_none()
    )
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


@router.get("/{token}/zip/download")
def download_public_album_zip(
    share: ShareLink = Depends(require_share_link),
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
) -> Response:
    record = album_zip_record(db, share.album_id)
    if not album_zip_ready(record):
        raise HTTPException(status_code=404, detail="zip not found")
    zip_path = album_zip_path(record, config.paths.derived)
    try:
        zip_path.stat()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="zip not found") from exc
    filename = f"album-{share.album_id}.zip"
    headers = {"Cache-Control": "private, max-age=60"}
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        headers=headers,
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


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
