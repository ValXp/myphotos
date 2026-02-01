from __future__ import annotations

from datetime import datetime, timezone
import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_config, get_db, require_owner_session
from app.auth.sessions import Session as OwnerSession
from app.config import Config
from app.db.enums import AssetVariantKind
from app.db.models import Album, AlbumItem, Asset, AssetVariant, ShareLink
from app.downloads.zip_jobs import (
    ZipFailedError,
    ZipInProgressError,
    album_zip_path,
    album_zip_ready,
    album_zip_record,
    invalidate_album_zip,
    latest_zip_job,
    start_album_zip_job,
    zip_status_payload,
)

router = APIRouter(prefix="/albums")


@router.get("")
def list_albums(
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    counts = (
        db.query(
            AlbumItem.album_id,
            func.count(AlbumItem.asset_id).label("item_count"),
        )
        .join(Asset, AlbumItem.asset_id == Asset.id)
        .filter(Asset.gone.is_(False))
        .group_by(AlbumItem.album_id)
        .subquery()
    )
    rows = (
        db.query(Album, func.coalesce(counts.c.item_count, 0))
        .outerjoin(counts, counts.c.album_id == Album.id)
        .order_by(Album.updated_at.desc(), Album.id.desc())
        .all()
    )
    items = [_serialize_album(album, int(count)) for album, count in rows]
    return {"items": items}


@router.get("/{album_id}")
def get_album(
    album_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    item_count = _album_item_count(db, album.id)
    return _serialize_album(album, item_count)


@router.get("/{album_id}/assets")
def list_album_assets(
    album_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    rows = (
        db.query(AlbumItem, Asset)
        .join(Asset, AlbumItem.asset_id == Asset.id)
        .filter(AlbumItem.album_id == album_id)
        .filter(Asset.gone.is_(False))
        .order_by(AlbumItem.order_index.asc(), AlbumItem.asset_id.asc())
        .all()
    )
    assets = [asset for _, asset in rows]
    asset_ids = [asset.id for asset in assets if asset.id]
    variants_by_asset: dict[str, list[AssetVariant]] = {}
    if asset_ids:
        variant_rows = (
            db.query(AssetVariant)
            .filter(AssetVariant.asset_id.in_(asset_ids))
            .all()
        )
        for variant in variant_rows:
            variants_by_asset.setdefault(variant.asset_id, []).append(variant)
    items = [
        _serialize_asset_summary(asset, variants=variants_by_asset.get(asset.id, []))
        for _, asset in rows
    ]
    return {"items": items}


@router.post("")
def create_album(
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    title = _require_title(payload)
    album = Album(title=title)
    db.add(album)
    db.commit()
    db.refresh(album)
    return _serialize_album(album, item_count=0)


@router.patch("/{album_id}")
def update_album(
    album_id: str,
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    title = _require_title(payload)
    album.title = title
    db.commit()
    db.refresh(album)
    item_count = _album_item_count(db, album.id)
    return _serialize_album(album, item_count)


@router.delete("/{album_id}")
def delete_album(
    album_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    db.delete(album)
    db.commit()
    return {"status": "deleted"}


@router.post("/{album_id}/items")
def add_album_items(
    album_id: str,
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    asset_ids = _require_asset_ids(payload)
    existing_assets = {
        row[0]
        for row in db.query(Asset.id).filter(Asset.id.in_(asset_ids)).all()
    }
    missing_assets = [asset_id for asset_id in asset_ids if asset_id not in existing_assets]
    if missing_assets:
        raise HTTPException(status_code=404, detail="asset not found")
    existing_items = {
        row[0]
        for row in db.query(AlbumItem.asset_id)
        .filter(AlbumItem.album_id == album_id)
        .filter(AlbumItem.asset_id.in_(asset_ids))
        .all()
    }
    new_ids = [asset_id for asset_id in asset_ids if asset_id not in existing_items]
    skipped_ids = [asset_id for asset_id in asset_ids if asset_id in existing_items]
    if new_ids:
        max_order = (
            db.query(func.max(AlbumItem.order_index))
            .filter(AlbumItem.album_id == album_id)
            .scalar()
        )
        next_index = 0 if max_order is None else int(max_order) + 1
        for offset, asset_id in enumerate(new_ids):
            db.add(
                AlbumItem(
                    album_id=album_id,
                    asset_id=asset_id,
                    order_index=next_index + offset,
                )
            )
        album.updated_at = datetime.now(timezone.utc)
        invalidate_album_zip(db, album_id)
    db.commit()
    item_count = _album_item_count(db, album_id)
    return {"added": new_ids, "skipped": skipped_ids, "item_count": item_count}


@router.delete("/{album_id}/items")
def remove_album_items(
    album_id: str,
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    asset_ids = _require_asset_ids(payload)
    items = (
        db.query(AlbumItem)
        .filter(AlbumItem.album_id == album_id)
        .filter(AlbumItem.asset_id.in_(asset_ids))
        .all()
    )
    removed_ids = [item.asset_id for item in items]
    missing_ids = [asset_id for asset_id in asset_ids if asset_id not in removed_ids]
    for item in items:
        db.delete(item)
    if removed_ids:
        album.updated_at = datetime.now(timezone.utc)
        invalidate_album_zip(db, album_id)
    db.commit()
    item_count = _album_item_count(db, album_id)
    return {"removed": removed_ids, "missing": missing_ids, "item_count": item_count}


@router.get("/{album_id}/shares")
def list_share_links(
    album_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    shares = (
        db.query(ShareLink)
        .filter(ShareLink.album_id == album_id)
        .order_by(ShareLink.created_at.desc(), ShareLink.id.desc())
        .all()
    )
    return {"items": [_serialize_share_link(share) for share in shares]}


@router.post("/{album_id}/shares")
def create_share_link(
    album_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    token = _generate_share_token(db)
    share = ShareLink(album_id=album_id, token=token)
    db.add(share)
    db.commit()
    db.refresh(share)
    return _serialize_share_link(share)


@router.delete("/{album_id}/shares/{share_id}")
def revoke_share_link(
    album_id: str,
    share_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    share = (
        db.query(ShareLink)
        .filter(ShareLink.id == share_id)
        .filter(ShareLink.album_id == album_id)
        .one_or_none()
    )
    if share is None:
        raise HTTPException(status_code=404, detail="share not found")
    if share.revoked_at is None:
        share.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(share)
    return _serialize_share_link(share)


@router.post("/{album_id}/zip")
def create_album_zip_job(
    album_id: str,
    response: Response,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    try:
        job = start_album_zip_job(db, album_id, config)
    except ZipInProgressError as exc:
        response.status_code = 409
        return zip_status_payload(exc.job, album_zip_record(db, album_id), album_id)
    except ZipFailedError as exc:
        response.status_code = 500
        return zip_status_payload(exc.job, album_zip_record(db, album_id), album_id)
    return zip_status_payload(job, album_zip_record(db, album_id), album_id)


@router.get("/{album_id}/zip")
def get_album_zip_status(
    album_id: str,
    db: Session = Depends(get_db),
    _: OwnerSession = Depends(require_owner_session),
) -> dict[str, object]:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    job = latest_zip_job(db, album_id)
    return zip_status_payload(job, album_zip_record(db, album_id), album_id)


@router.get("/{album_id}/zip/download")
def download_album_zip(
    album_id: str,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    _: OwnerSession = Depends(require_owner_session),
) -> Response:
    album = db.query(Album).filter(Album.id == album_id).one_or_none()
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    record = album_zip_record(db, album_id)
    if not album_zip_ready(record):
        raise HTTPException(status_code=404, detail="zip not found")
    zip_path = album_zip_path(record, config.paths.derived)
    try:
        zip_path.stat()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="zip not found") from exc
    filename = f"album-{album_id}.zip"
    headers = {"Cache-Control": "private, max-age=60"}
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        headers=headers,
    )


def _serialize_album(album: Album, item_count: int) -> dict[str, object]:
    return {
        "id": album.id,
        "title": album.title,
        "created_at": _isoformat(album.created_at),
        "updated_at": _isoformat(album.updated_at),
        "item_count": item_count,
    }


def _serialize_share_link(share: ShareLink) -> dict[str, object]:
    return {
        "id": share.id,
        "album_id": share.album_id,
        "token": share.token,
        "created_at": _isoformat(share.created_at),
        "revoked_at": _isoformat(share.revoked_at),
    }


def _serialize_asset_summary(
    asset: Asset,
    *,
    variants: list[AssetVariant] | None = None,
) -> dict[str, object]:
    variants = variants or []

    def has_variant(kind: AssetVariantKind, profile: str | None = None) -> bool:
        for variant in variants:
            if variant.kind != kind:
                continue
            if profile is None or variant.profile == profile:
                return True
        return False

    ready = {
        "thumb": has_variant(AssetVariantKind.thumb, "thumb_md"),
        "stream": has_variant(AssetVariantKind.video_transcode),
        "live": has_variant(AssetVariantKind.live_video),
    }

    return {
        "id": asset.id,
        "type": asset.type,
        "captured_at": _isoformat(asset.captured_at),
        "created_at": _isoformat(asset.created_at),
        "duration_ms": asset.duration_ms,
        "width": asset.width,
        "height": asset.height,
        "live_photo_video_id": asset.live_photo_video_id,
        "ready": ready,
    }


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _require_title(payload: dict[str, object]) -> str:
    raw = payload.get("title")
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="title required")
    title = raw.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    return title


def _require_asset_ids(payload: dict[str, object]) -> list[str]:
    raw = payload.get("asset_ids")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="asset_ids required")
    seen: set[str] = set()
    asset_ids: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail="asset_ids must be strings")
        asset_id = value.strip()
        if not asset_id:
            raise HTTPException(status_code=400, detail="asset_ids must be non-empty")
        if asset_id in seen:
            continue
        seen.add(asset_id)
        asset_ids.append(asset_id)
    if not asset_ids:
        raise HTTPException(status_code=400, detail="asset_ids required")
    return asset_ids


def _generate_share_token(db: Session) -> str:
    for _ in range(5):
        token = secrets.token_urlsafe(32)
        exists = (
            db.query(ShareLink.id)
            .filter(ShareLink.token == token)
            .first()
        )
        if exists is None:
            return token
    raise HTTPException(status_code=500, detail="share token generation failed")


def _album_item_count(db: Session, album_id: str) -> int:
    count = (
        db.query(func.count(AlbumItem.asset_id))
        .join(Asset, AlbumItem.asset_id == Asset.id)
        .filter(AlbumItem.album_id == album_id)
        .filter(Asset.gone.is_(False))
        .scalar()
    )
    return int(count or 0)
