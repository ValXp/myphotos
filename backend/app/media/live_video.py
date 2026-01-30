from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetType
from app.db.models import Asset, AssetVariant
from app.media.variants import LIVE_VIDEO_PROFILE, build_variant_record, variant_output_path


class LiveVideoError(RuntimeError):
    pass


class LiveVideoNotFoundError(LiveVideoError):
    pass


class LiveVideoToolError(LiveVideoError):
    pass


LiveVideoGenerator = Callable[[Path, Path], None]


def live_video_output_path(derived_root: Path, asset_id: str) -> Path:
    return variant_output_path(derived_root, asset_id, LIVE_VIDEO_PROFILE)


def run_live_video_job(
    session: Session,
    asset_id: str,
    *,
    derived_root: Path,
    ffmpeg_path: str = "ffmpeg",
    generator: LiveVideoGenerator | None = None,
) -> AssetVariant:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise LiveVideoNotFoundError(f"asset not found: {asset_id}")
    if asset.type != AssetType.live_photo:
        raise LiveVideoError(f"unsupported asset type: {asset.type}")
    if not asset.live_photo_video_id:
        raise LiveVideoError("live photo video link is missing")

    video_asset = session.get(Asset, asset.live_photo_video_id)
    if video_asset is None:
        raise LiveVideoNotFoundError(
            f"live photo video asset not found: {asset.live_photo_video_id}"
        )

    source_path = Path(video_asset.original_path)
    if not source_path.exists():
        raise LiveVideoError(f"file not found: {source_path}")

    output_path = live_video_output_path(derived_root, asset.id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    renderer = generator or (
        lambda source, output: _transcode_live_video(
            source, output, ffmpeg_path=ffmpeg_path
        )
    )
    renderer(source_path, output_path)
    if not output_path.exists():
        raise LiveVideoError(f"live video output missing: {output_path}")

    record = build_variant_record(
        derived_root,
        asset.id,
        LIVE_VIDEO_PROFILE,
        size_bytes=output_path.stat().st_size,
    )
    variant = _upsert_variant(session, record)
    session.flush()
    return variant


def _upsert_variant(session: Session, record: AssetVariant) -> AssetVariant:
    existing = session.execute(
        select(AssetVariant).where(
            AssetVariant.asset_id == record.asset_id,
            AssetVariant.kind == record.kind,
            AssetVariant.profile == record.profile,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.path = record.path
        existing.bytes = record.bytes
        return existing
    session.add(record)
    return record


def _transcode_live_video(source_path: Path, output_path: Path, *, ffmpeg_path: str) -> None:
    if shutil.which(ffmpeg_path) is None:
        raise LiveVideoToolError("ffmpeg is required for live photo videos")

    subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
