from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetType
from app.db.models import Asset
from app.ingest.file_types import find_live_photo_pairs


@dataclass(frozen=True)
class LivePhotoLink:
    still_id: str
    video_id: str


LIVE_PHOTO_MIN_DURATION_MS = 1500
LIVE_PHOTO_MAX_DURATION_MS = 3500
LIVE_PHOTO_MAX_CAPTURE_DELTA_SECONDS = 2.0


def link_live_photo_pairs(
    session: Session,
    *,
    assets: Iterable[Asset] | None = None,
) -> list[LivePhotoLink]:
    if assets is None:
        assets = session.execute(select(Asset)).scalars().all()
    else:
        assets = list(assets)

    path_to_asset: dict[str, Asset] = {}
    used_video_ids: set[str] = set()
    used_still_ids: set[str] = set()
    for asset in assets:
        if asset.live_photo_video_id:
            used_video_ids.add(asset.live_photo_video_id)
            if asset.id:
                used_still_ids.add(asset.id)
        if not asset.original_path:
            continue
        path_to_asset[str(Path(asset.original_path))] = asset

    pairs = find_live_photo_pairs(path_to_asset.keys())
    links: list[LivePhotoLink] = []
    for pair in pairs:
        still = path_to_asset.get(str(pair.still))
        video = path_to_asset.get(str(pair.video))
        if still is None or video is None:
            continue
        if not still.id or not video.id:
            continue
        if _apply_live_photo_link(still, video, used_video_ids=used_video_ids):
            links.append(LivePhotoLink(still_id=still.id, video_id=video.id))
            used_video_ids.add(video.id)
            used_still_ids.add(still.id)
    links.extend(
        _link_live_photo_metadata_pairs(
            assets,
            used_still_ids=used_still_ids,
            used_video_ids=used_video_ids,
        )
    )
    return links


def _apply_live_photo_link(still: Asset, video: Asset, *, used_video_ids: set[str]) -> bool:
    if video.id in used_video_ids and still.live_photo_video_id != video.id:
        return False
    updated = False
    if still.type != AssetType.live_photo:
        still.type = AssetType.live_photo
        updated = True
    if still.live_photo_video_id != video.id:
        still.live_photo_video_id = video.id
        updated = True
    return updated


def _link_live_photo_metadata_pairs(
    assets: Iterable[Asset],
    *,
    used_still_ids: set[str],
    used_video_ids: set[str],
) -> list[LivePhotoLink]:
    stills_by_parent: dict[Path, list[Asset]] = {}
    videos: list[Asset] = []
    for asset in assets:
        if not asset.original_path or not asset.id:
            continue
        if asset.type == AssetType.video:
            videos.append(asset)
            continue
        if asset.live_photo_video_id:
            continue
        if asset.id in used_still_ids:
            continue
        if asset.type not in {AssetType.photo, AssetType.live_photo}:
            continue
        parent = Path(asset.original_path).parent
        stills_by_parent.setdefault(parent, []).append(asset)

    links: list[LivePhotoLink] = []
    for video in videos:
        if not video.id or video.id in used_video_ids:
            continue
        if not _is_live_photo_duration(video.duration_ms):
            continue
        parent = Path(video.original_path).parent if video.original_path else None
        if parent is None:
            continue
        candidates = stills_by_parent.get(parent)
        if not candidates:
            continue
        match = _best_still_candidate(video, candidates, used_still_ids)
        if match is None:
            continue
        if _apply_live_photo_link(match, video, used_video_ids=used_video_ids):
            links.append(LivePhotoLink(still_id=match.id, video_id=video.id))
            used_video_ids.add(video.id)
            used_still_ids.add(match.id)
    return links


def _best_still_candidate(
    video: Asset,
    candidates: list[Asset],
    used_still_ids: set[str],
) -> Asset | None:
    video_time = _asset_timestamp(video)
    if video_time is None:
        return None
    best: Asset | None = None
    best_delta: float | None = None
    best_similarity = -1
    for still in candidates:
        if not still.id or still.id in used_still_ids:
            continue
        still_time = _asset_timestamp(still)
        if still_time is None:
            continue
        delta = abs((still_time - video_time).total_seconds())
        if delta > LIVE_PHOTO_MAX_CAPTURE_DELTA_SECONDS:
            continue
        similarity = _name_similarity(still, video)
        if best is None or best_delta is None or delta < best_delta:
            best = still
            best_delta = delta
            best_similarity = similarity
            continue
        if best_delta is not None and delta == best_delta and similarity > best_similarity:
            best = still
            best_similarity = similarity
    return best


def _name_similarity(still: Asset, video: Asset) -> int:
    if not still.original_path or not video.original_path:
        return 0
    still_stem = Path(still.original_path).stem.casefold()
    video_stem = Path(video.original_path).stem.casefold()
    return len(os.path.commonprefix([still_stem, video_stem]))


def _asset_timestamp(asset: Asset) -> datetime | None:
    if asset.captured_at is not None:
        return asset.captured_at
    if asset.original_mtime_ns is None:
        return None
    return datetime.fromtimestamp(asset.original_mtime_ns / 1_000_000_000, tz=timezone.utc)


def _is_live_photo_duration(duration_ms: int | None) -> bool:
    if duration_ms is None:
        return False
    return LIVE_PHOTO_MIN_DURATION_MS <= duration_ms <= LIVE_PHOTO_MAX_DURATION_MS
