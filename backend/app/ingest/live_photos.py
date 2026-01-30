from __future__ import annotations

from dataclasses import dataclass
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


def link_live_photo_pairs(
    session: Session,
    *,
    assets: Iterable[Asset] | None = None,
) -> list[LivePhotoLink]:
    if assets is None:
        assets = session.execute(select(Asset)).scalars().all()

    path_to_asset: dict[str, Asset] = {}
    for asset in assets:
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
        if _apply_live_photo_link(still, video):
            links.append(LivePhotoLink(still_id=still.id, video_id=video.id))
    return links


def _apply_live_photo_link(still: Asset, video: Asset) -> bool:
    updated = False
    if still.type != AssetType.live_photo:
        still.type = AssetType.live_photo
        updated = True
    if still.live_photo_video_id != video.id:
        still.live_photo_video_id = video.id
        updated = True
    return updated
