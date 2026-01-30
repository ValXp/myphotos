from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = frozenset(
    {
        "avif",
        "bmp",
        "dng",
        "gif",
        "heic",
        "heif",
        "jpeg",
        "jpg",
        "png",
        "tif",
        "tiff",
        "webp",
    }
)

VIDEO_EXTENSIONS = frozenset(
    {
        "3g2",
        "3gp",
        "avi",
        "m4v",
        "mkv",
        "mov",
        "mp4",
        "mpeg",
        "mpg",
        "webm",
    }
)


@dataclass(frozen=True)
class LivePhotoPair:
    still: Path
    video: Path


def normalize_extension(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix.startswith("."):
        return suffix[1:]
    return suffix


def is_image(path: str | Path) -> bool:
    return normalize_extension(path) in IMAGE_EXTENSIONS


def is_video(path: str | Path) -> bool:
    return normalize_extension(path) in VIDEO_EXTENSIONS


def is_supported(path: str | Path) -> bool:
    return is_image(path) or is_video(path)


def is_live_photo_pair(path_a: str | Path, path_b: str | Path) -> bool:
    path_a = Path(path_a)
    path_b = Path(path_b)
    if is_image(path_a) and is_video(path_b):
        return _pair_matches(path_a, path_b)
    if is_image(path_b) and is_video(path_a):
        return _pair_matches(path_b, path_a)
    return False


def find_live_photo_pairs(paths: Iterable[str | Path]) -> list[LivePhotoPair]:
    buckets: dict[tuple[Path, str], dict[str, Path]] = {}
    for item in paths:
        path = Path(item)
        key = _pair_key(path)
        if key is None:
            continue
        bucket = buckets.setdefault(key, {})
        if is_image(path):
            bucket.setdefault("still", path)
        elif is_video(path):
            bucket.setdefault("video", path)
    pairs: list[LivePhotoPair] = []
    for bucket in buckets.values():
        still = bucket.get("still")
        video = bucket.get("video")
        if still is not None and video is not None:
            pairs.append(LivePhotoPair(still=still, video=video))
    return pairs


def _pair_key(path: Path) -> tuple[Path, str] | None:
    if not is_supported(path):
        return None
    return (path.parent, _stem_key(path))


def _pair_matches(still: Path, video: Path) -> bool:
    return still.parent == video.parent and _stem_key(still) == _stem_key(video)


def _stem_key(path: Path) -> str:
    return path.stem.casefold()
