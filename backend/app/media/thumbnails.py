from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetType
from app.db.models import Asset, AssetVariant
from app.media.variants import (
    THUMBNAIL_PROFILES,
    VIDEO_POSTER_PROFILE,
    VariantProfile,
    build_variant_record,
    variant_output_path,
)

DEFAULT_THUMB_QUALITY = 85


class ThumbnailError(RuntimeError):
    pass


class ThumbnailToolError(ThumbnailError):
    pass


class ThumbnailNotFoundError(ThumbnailError):
    pass


PosterExtractor = Callable[[Path, Path], None]


def compute_thumbnail_size(
    original_width: int,
    original_height: int,
    target_width: int | None,
    target_height: int | None,
    *,
    allow_upscale: bool = False,
) -> tuple[int, int]:
    if original_width <= 0 or original_height <= 0:
        raise ValueError("original dimensions must be positive")
    if target_width is not None and target_width <= 0:
        raise ValueError("target_width must be positive")
    if target_height is not None and target_height <= 0:
        raise ValueError("target_height must be positive")

    scale = _compute_scale(
        original_width,
        original_height,
        target_width,
        target_height,
        allow_upscale=allow_upscale,
    )
    width = max(1, int(round(original_width * scale)))
    height = max(1, int(round(original_height * scale)))
    return width, height


def thumbnail_profiles_for_asset(asset_type: AssetType) -> tuple[VariantProfile, ...]:
    if asset_type == AssetType.photo:
        return THUMBNAIL_PROFILES
    if asset_type in {AssetType.video, AssetType.live_photo}:
        return THUMBNAIL_PROFILES + (VIDEO_POSTER_PROFILE,)
    raise ThumbnailError(f"unsupported asset type: {asset_type}")


def run_thumbnail_job(
    session: Session,
    asset_id: str,
    *,
    derived_root: Path,
    vips_module: object | None = None,
    ffmpeg_path: str = "ffmpeg",
    poster_extractor: PosterExtractor | None = None,
    quality: int = DEFAULT_THUMB_QUALITY,
) -> list[AssetVariant]:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise ThumbnailNotFoundError(f"asset not found: {asset_id}")
    if not asset.id:
        raise ThumbnailError("asset id is required")

    source_path = Path(asset.original_path)
    profiles = thumbnail_profiles_for_asset(asset.type)

    if asset.type == AssetType.photo:
        return _generate_thumbnails(
            session,
            source_path,
            asset.id,
            derived_root,
            profiles,
            vips_module=vips_module,
            quality=quality,
        )

    if asset.type in {AssetType.video, AssetType.live_photo}:
        if not source_path.exists():
            raise ThumbnailError(f"file not found: {source_path}")
        extractor = poster_extractor or (
            lambda video_path, poster_path: _extract_video_poster(
                video_path, poster_path, ffmpeg_path=ffmpeg_path
            )
        )
        with TemporaryDirectory() as tmpdir:
            poster_path = Path(tmpdir) / "poster.jpg"
            extractor(source_path, poster_path)
            if not poster_path.exists():
                raise ThumbnailError("poster extraction failed")
            return _generate_thumbnails(
                session,
                poster_path,
                asset.id,
                derived_root,
                profiles,
                vips_module=vips_module,
                quality=quality,
            )

    raise ThumbnailError(f"unsupported asset type: {asset.type}")


def _compute_scale(
    original_width: int,
    original_height: int,
    target_width: int | None,
    target_height: int | None,
    *,
    allow_upscale: bool,
) -> float:
    if target_width is None and target_height is None:
        return 1.0
    if target_width is None:
        scale = target_height / original_height
    elif target_height is None:
        scale = target_width / original_width
    else:
        scale = min(target_width / original_width, target_height / original_height)
    if not allow_upscale:
        scale = min(scale, 1.0)
    return scale


def _generate_thumbnails(
    session: Session,
    source_path: Path,
    asset_id: str,
    derived_root: Path,
    profiles: Iterable[VariantProfile],
    *,
    vips_module: object | None,
    quality: int,
) -> list[AssetVariant]:
    if not source_path.exists():
        raise ThumbnailError(f"file not found: {source_path}")
    vips = _load_vips(vips_module)
    image = vips.Image.new_from_file(str(source_path), access="sequential")

    variants: list[AssetVariant] = []
    for profile in profiles:
        resized = _resize_image(image, profile.width, profile.height)
        output_file = variant_output_path(derived_root, asset_id, profile)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        resized.write_to_file(str(output_file), Q=quality, strip=True)
        record = build_variant_record(
            derived_root,
            asset_id,
            profile,
            size_bytes=output_file.stat().st_size,
        )
        variants.append(_upsert_variant(session, record))
    session.flush()
    return variants


def _resize_image(image: object, target_width: int | None, target_height: int | None) -> object:
    width = int(getattr(image, "width"))
    height = int(getattr(image, "height"))
    scale = _compute_scale(width, height, target_width, target_height, allow_upscale=False)
    if scale == 1.0:
        return image
    return image.resize(scale, kernel="lanczos3")


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


def _load_vips(vips_module: object | None) -> object:
    if vips_module is not None:
        return vips_module
    try:
        import pyvips  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ThumbnailToolError("pyvips is required for thumbnail generation") from exc
    return pyvips


def _extract_video_poster(video_path: Path, poster_path: Path, *, ffmpeg_path: str) -> None:
    if not video_path.exists():
        raise ThumbnailError(f"file not found: {video_path}")
    if shutil.which(ffmpeg_path) is None:
        raise ThumbnailToolError("ffmpeg is required for video poster extraction")
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(poster_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
