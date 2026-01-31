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
    # When True, this rendition should preserve HDR (10-bit) if the source is HDR.
    hdr: bool = False

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

LIVE_VIDEO_PROFILE = VariantProfile(
    "live",
    AssetVariantKind.live_video,
    "mp4",
)

DEFAULT_VIDEO_RENDITION_PROFILES: tuple[VariantProfile, ...] = (
    VariantProfile(
        "360p",
        AssetVariantKind.video_transcode,
        "m3u8",
        width=640,
        height=360,
        video_bitrate_kbps=800,
        audio_bitrate_kbps=96,
    ),
    VariantProfile(
        "720p",
        AssetVariantKind.video_transcode,
        "m3u8",
        width=1280,
        height=720,
        video_bitrate_kbps=2800,
        audio_bitrate_kbps=128,
    ),
    VariantProfile(
        "1080p",
        AssetVariantKind.video_transcode,
        "m3u8",
        width=1920,
        height=1080,
        video_bitrate_kbps=5000,
        audio_bitrate_kbps=192,
    ),
)

# Backwards-compatible alias for older imports/tests.
VIDEO_RENDITION_PROFILES = DEFAULT_VIDEO_RENDITION_PROFILES


def profiles_for_asset_type(asset_type: AssetType) -> tuple[VariantProfile, ...]:
    if asset_type == AssetType.photo:
        return THUMBNAIL_PROFILES
    if asset_type == AssetType.video:
        return THUMBNAIL_PROFILES + (VIDEO_POSTER_PROFILE,) + DEFAULT_VIDEO_RENDITION_PROFILES
    if asset_type == AssetType.live_photo:
        return THUMBNAIL_PROFILES + (LIVE_VIDEO_PROFILE,) + DEFAULT_VIDEO_RENDITION_PROFILES
    raise ValueError(f"Unsupported asset type: {asset_type}")


def video_renditions_from_config(
    renditions: list[dict[str, object]] | None,
    *,
    source_width: int | None,
    source_height: int | None,
    source_is_hdr: bool,
) -> tuple[VariantProfile, ...]:
    """Build transcode rendition profiles from config.

    Rendition dict schema:
      name, width, height, video_bitrate_kbps, audio_bitrate_kbps
      min_source_width (optional), min_source_height (optional)

    A rendition with min_source_* is only included if the source dimensions are known
    and meet the minimum.
    """

    if not renditions:
        return DEFAULT_VIDEO_RENDITION_PROFILES

    profiles: list[VariantProfile] = []
    for rendition in renditions:
        name = str(rendition.get("name") or "").strip()
        width = rendition.get("width")
        height = rendition.get("height")
        video_bitrate_kbps = rendition.get("video_bitrate_kbps")
        audio_bitrate_kbps = rendition.get("audio_bitrate_kbps")
        hdr = rendition.get("hdr")
        hdr_flag = bool(hdr) if isinstance(hdr, bool) else False
        if not name or not isinstance(width, int) or not isinstance(height, int):
            continue
        if not isinstance(video_bitrate_kbps, int) or not isinstance(audio_bitrate_kbps, int):
            continue

        # HDR renditions are only produced for HDR sources.
        if hdr_flag and not source_is_hdr:
            continue

        min_w = rendition.get("min_source_width")
        min_h = rendition.get("min_source_height")
        if isinstance(min_w, int) or isinstance(min_h, int):
            if source_width is None or source_height is None:
                continue
            if isinstance(min_w, int) and source_width < min_w:
                continue
            if isinstance(min_h, int) and source_height < min_h:
                continue

        profiles.append(
            VariantProfile(
                name,
                AssetVariantKind.video_transcode,
                "m3u8",
                width=width,
                height=height,
                video_bitrate_kbps=video_bitrate_kbps,
                audio_bitrate_kbps=audio_bitrate_kbps,
                hdr=hdr_flag,
            )
        )

    return tuple(profiles) if profiles else DEFAULT_VIDEO_RENDITION_PROFILES


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
