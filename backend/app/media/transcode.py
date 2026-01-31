from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetType, AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.media.live_video import LiveVideoGenerator, run_live_video_job
from app.media.variants import (
    VariantProfile,
    build_variant_record,
    variant_output_path,
    video_renditions_from_config,
)

DEFAULT_HLS_TIME_SECONDS = 4


class TranscodeError(RuntimeError):
    pass


class TranscodeToolError(TranscodeError):
    pass


class TranscodeNotFoundError(TranscodeError):
    pass


TranscodeFunc = Callable[[Path, Path, Path, VariantProfile], None]


def transcode_profiles_for_asset(
    asset_type: AssetType,
    *,
    renditions: list[dict[str, object]] | None,
    source_width: int | None,
    source_height: int | None,
) -> tuple[VariantProfile, ...]:
    if asset_type in {AssetType.video, AssetType.live_photo}:
        return video_renditions_from_config(
            renditions,
            source_width=source_width,
            source_height=source_height,
        )
    raise TranscodeError(f"unsupported asset type: {asset_type}")


def transcode_playlist_path(derived_root: Path, asset_id: str, profile: VariantProfile) -> Path:
    return variant_output_path(derived_root, asset_id, profile)


def transcode_segment_pattern(derived_root: Path, asset_id: str, profile: VariantProfile) -> Path:
    playlist_path = transcode_playlist_path(derived_root, asset_id, profile)
    return playlist_path.with_name(f"{profile.name}_%03d.ts")


def format_segment_path(segment_pattern: Path, index: int) -> Path:
    return Path(str(segment_pattern) % index)


def master_manifest_path(derived_root: Path, asset_id: str) -> Path:
    return derived_root / asset_id / AssetVariantKind.video_transcode.value / "master.m3u8"


def build_master_manifest(profiles: Iterable[VariantProfile]) -> str:
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    for profile in profiles:
        bandwidth = _profile_bandwidth(profile)
        stream_inf = f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth}"
        if profile.width is not None and profile.height is not None:
            stream_inf = f"{stream_inf},RESOLUTION={profile.width}x{profile.height}"
        lines.append(stream_inf)
        lines.append(profile.filename())
    return "\n".join(lines) + "\n"


def run_transcode_job(
    session: Session,
    asset_id: str,
    *,
    derived_root: Path,
    config: object | None = None,
    ffmpeg_path: str = "ffmpeg",
    transcode_func: TranscodeFunc | None = None,
    live_video_generator: LiveVideoGenerator | None = None,
) -> list[AssetVariant]:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise TranscodeNotFoundError(f"asset not found: {asset_id}")
    if not asset.id:
        raise TranscodeError("asset id is required")
    if asset.type not in {AssetType.video, AssetType.live_photo}:
        raise TranscodeError(f"unsupported asset type: {asset.type}")

    source_path = _resolve_transcode_source(session, asset)
    if not source_path.exists():
        raise TranscodeError(f"file not found: {source_path}")

    renditions = None
    if config is not None and hasattr(config, "media") and hasattr(config.media, "video_renditions"):
        try:
            renditions = list(config.media.video_renditions)
        except TypeError:
            renditions = None

    profiles = transcode_profiles_for_asset(
        asset.type,
        renditions=renditions,
        source_width=asset.width,
        source_height=asset.height,
    )
    transcoder = transcode_func or (
        lambda source, playlist, segment_pattern, profile: _transcode_profile(
            source,
            playlist,
            segment_pattern,
            profile,
            ffmpeg_path=ffmpeg_path,
        )
    )

    variants: list[AssetVariant] = []
    for profile in profiles:
        playlist_path = transcode_playlist_path(derived_root, asset.id, profile)
        segment_pattern = transcode_segment_pattern(derived_root, asset.id, profile)
        playlist_path.parent.mkdir(parents=True, exist_ok=True)
        transcoder(source_path, playlist_path, segment_pattern, profile)
        if not playlist_path.exists():
            raise TranscodeError(f"transcode output missing: {playlist_path}")
        record = build_variant_record(
            derived_root,
            asset.id,
            profile,
            size_bytes=playlist_path.stat().st_size,
        )
        variants.append(_upsert_variant(session, record))

    manifest_path = master_manifest_path(derived_root, asset.id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(build_master_manifest(profiles), encoding="ascii")
    if asset.type == AssetType.live_photo:
        live_variant = run_live_video_job(
            session,
            asset.id,
            derived_root=derived_root,
            ffmpeg_path=ffmpeg_path,
            generator=live_video_generator,
        )
        variants.append(live_variant)
    session.flush()
    return variants


def _resolve_transcode_source(session: Session, asset: Asset) -> Path:
    if asset.type == AssetType.video:
        return Path(asset.original_path)
    if asset.type == AssetType.live_photo:
        if not asset.live_photo_video_id:
            raise TranscodeError("live photo video link is missing")
        video_asset = session.get(Asset, asset.live_photo_video_id)
        if video_asset is None:
            raise TranscodeNotFoundError(
                f"live photo video asset not found: {asset.live_photo_video_id}"
            )
        return Path(video_asset.original_path)
    raise TranscodeError(f"unsupported asset type: {asset.type}")


def _profile_bandwidth(profile: VariantProfile) -> int:
    video_kbps = profile.video_bitrate_kbps or 0
    audio_kbps = profile.audio_bitrate_kbps or 0
    return (video_kbps + audio_kbps) * 1000


def _transcode_profile(
    source_path: Path,
    playlist_path: Path,
    segment_pattern: Path,
    profile: VariantProfile,
    *,
    ffmpeg_path: str,
    hls_time_seconds: int = DEFAULT_HLS_TIME_SECONDS,
) -> None:
    if not source_path.exists():
        raise TranscodeError(f"file not found: {source_path}")
    if shutil.which(ffmpeg_path) is None:
        raise TranscodeToolError("ffmpeg is required for video transcodes")
    if profile.width is None or profile.height is None:
        raise TranscodeError("transcode profile requires width and height")
    if profile.video_bitrate_kbps is None or profile.audio_bitrate_kbps is None:
        raise TranscodeError("transcode profile requires bitrate settings")

    playlist_path.parent.mkdir(parents=True, exist_ok=True)
    segment_pattern.parent.mkdir(parents=True, exist_ok=True)
    scale_filter = (
        f"scale=w={profile.width}:h={profile.height}:force_original_aspect_ratio=decrease"
    )

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
            "-map",
            "0:a:0?",
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-profile:v",
            "main",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            f"{profile.video_bitrate_kbps}k",
            "-maxrate",
            f"{profile.video_bitrate_kbps}k",
            "-bufsize",
            f"{profile.video_bitrate_kbps * 2}k",
            "-c:a",
            "aac",
            "-b:a",
            f"{profile.audio_bitrate_kbps}k",
            "-ac",
            "2",
            "-f",
            "hls",
            "-hls_time",
            str(hls_time_seconds),
            "-hls_playlist_type",
            "vod",
            "-hls_flags",
            "independent_segments",
            "-hls_segment_filename",
            str(segment_pattern),
            str(playlist_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


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
