from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.db.enums import AssetType, AssetVariantKind
from app.db.models import AssetVariant


@dataclass(frozen=True)
class VariantProfile:
    name: str
    kind: AssetVariantKind
    extension: str
    width: int | None = None
    height: int | None = None
    video_bitrate_kbps: int | None = None
    audio_bitrate_kbps: int | None = None

    def filename(self) -> str:
        return f"{self.name}.{self.extension}"


THUMBNAIL_PROFILES: tuple[VariantProfile, ...] = (
    VariantProfile("thumb_sm", AssetVariantKind.thumb, "jpg", width=256, height=256),
    VariantProfile("thumb_md", AssetVariantKind.thumb, "jpg", width=512, height=512),
    VariantProfile("thumb_lg", AssetVariantKind.thumb, "jpg", width=1024, height=1024),
)

VIDEO_POSTER_PROFILE = VariantProfile(
    "poster", AssetVariantKind.thumb, "jpg", width=1280, height=720
)

VIDEO_RENDITION_PROFILES: tuple[VariantProfile, ...] = (
    VariantProfile(
        "360p",
        AssetVariantKind.video_transcode,
        "mp4",
        width=640,
        height=360,
        video_bitrate_kbps=800,
        audio_bitrate_kbps=96,
    ),
    VariantProfile(
        "720p",
        AssetVariantKind.video_transcode,
        "mp4",
        width=1280,
        height=720,
        video_bitrate_kbps=2800,
        audio_bitrate_kbps=128,
    ),
    VariantProfile(
        "1080p",
        AssetVariantKind.video_transcode,
        "mp4",
        width=1920,
        height=1080,
        video_bitrate_kbps=5000,
        audio_bitrate_kbps=192,
    ),
)


def profiles_for_asset_type(asset_type: AssetType) -> tuple[VariantProfile, ...]:
    if asset_type == AssetType.photo:
        return THUMBNAIL_PROFILES
    if asset_type in {AssetType.video, AssetType.live_photo}:
        return THUMBNAIL_PROFILES + (VIDEO_POSTER_PROFILE,) + VIDEO_RENDITION_PROFILES
    raise ValueError(f"Unsupported asset type: {asset_type}")


def variant_output_path(derived_root: Path, asset_id: str, profile: VariantProfile) -> Path:
    if not asset_id:
        raise ValueError("asset_id is required")
    return derived_root / asset_id / profile.kind.value / profile.filename()


def build_variant_record(
    derived_root: Path,
    asset_id: str,
    profile: VariantProfile,
    *,
    size_bytes: int | None = None,
) -> AssetVariant:
    path = variant_output_path(derived_root, asset_id, profile)
    return AssetVariant(
        asset_id=asset_id,
        kind=profile.kind,
        profile=profile.name,
        path=str(path),
        bytes=size_bytes,
    )
