from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.db.models import Asset


class MetadataError(RuntimeError):
    pass


class MetadataToolError(MetadataError):
    pass


class MetadataParseError(MetadataError):
    pass


class MetadataNotFoundError(MetadataError):
    pass


@dataclass(frozen=True)
class MetadataResult:
    captured_at: datetime | None = None
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    lat: float | None = None
    lon: float | None = None

    def apply_to_asset(self, asset: Asset) -> None:
        if self.captured_at is not None:
            asset.captured_at = self.captured_at
        if self.duration_ms is not None:
            asset.duration_ms = self.duration_ms
        if self.width is not None:
            asset.width = self.width
        if self.height is not None:
            asset.height = self.height
        if self.lat is not None and self.lon is not None:
            asset.lat = self.lat
            asset.lon = self.lon


EXIF_DATE_KEYS = (
    "DateTimeOriginal",
    "CreateDate",
    "MediaCreateDate",
    "TrackCreateDate",
    "ModifyDate",
    "GPSDateTime",
)
EXIF_OFFSET_KEYS = (
    "OffsetTimeOriginal",
    "OffsetTimeDigitized",
    "OffsetTime",
)
EXIF_WIDTH_KEYS = (
    "ExifImageWidth",
    "ImageWidth",
    "SourceImageWidth",
)
EXIF_HEIGHT_KEYS = (
    "ExifImageHeight",
    "ImageHeight",
    "SourceImageHeight",
)


def run_metadata_job(
    session: Session,
    asset_id: str,
    *,
    exiftool_path: str = "exiftool",
    ffprobe_path: str = "ffprobe",
) -> MetadataResult:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise MetadataNotFoundError(f"asset not found: {asset_id}")
    metadata = extract_metadata(Path(asset.original_path), exiftool_path=exiftool_path, ffprobe_path=ffprobe_path)
    metadata.apply_to_asset(asset)
    session.add(asset)
    return metadata


def extract_metadata(
    path: Path,
    *,
    exiftool_path: str = "exiftool",
    ffprobe_path: str = "ffprobe",
) -> MetadataResult:
    if not path.exists():
        raise MetadataError(f"file not found: {path}")

    exiftool_result = MetadataResult()
    ffprobe_result = MetadataResult()
    exiftool_available = shutil.which(exiftool_path) is not None
    ffprobe_available = shutil.which(ffprobe_path) is not None

    if not exiftool_available and not ffprobe_available:
        raise MetadataToolError("exiftool or ffprobe must be installed")

    if exiftool_available:
        exiftool_result = _extract_exiftool(path, exiftool_path)
    if ffprobe_available:
        ffprobe_result = _extract_ffprobe(path, ffprobe_path)

    return merge_metadata(exiftool_result, ffprobe_result)


def merge_metadata(exif: MetadataResult, ffprobe: MetadataResult) -> MetadataResult:
    return MetadataResult(
        captured_at=_coalesce(exif.captured_at, ffprobe.captured_at),
        duration_ms=_coalesce(ffprobe.duration_ms, exif.duration_ms),
        width=_coalesce(ffprobe.width, exif.width),
        height=_coalesce(ffprobe.height, exif.height),
        lat=_coalesce(exif.lat, ffprobe.lat),
        lon=_coalesce(exif.lon, ffprobe.lon),
    )


def parse_exiftool_payload(payload: object) -> MetadataResult:
    if not isinstance(payload, list) or not payload:
        return MetadataResult()
    data = payload[0]
    if not isinstance(data, dict):
        return MetadataResult()

    offset = _first_string(data, EXIF_OFFSET_KEYS)
    captured_raw = _first_string(data, EXIF_DATE_KEYS)
    captured_at = _parse_exif_datetime(captured_raw, offset)

    width = _first_int(data, EXIF_WIDTH_KEYS)
    height = _first_int(data, EXIF_HEIGHT_KEYS)

    lat = _parse_float(data.get("GPSLatitude"))
    lon = _parse_float(data.get("GPSLongitude"))
    if lat is None or lon is None:
        lat = None
        lon = None

    return MetadataResult(
        captured_at=captured_at,
        width=width,
        height=height,
        lat=lat,
        lon=lon,
    )


def parse_ffprobe_payload(payload: object) -> MetadataResult:
    if not isinstance(payload, dict):
        return MetadataResult()

    width = None
    height = None
    rotation = None

    streams = payload.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            width = _parse_int(stream.get("width"))
            height = _parse_int(stream.get("height"))
            if width is not None and height is not None:
                rotation = _parse_int(stream.get("rotation"))
                if rotation is None:
                    rotation = _parse_int(_get_nested(stream, "tags", "rotate"))
                break

    if rotation in {90, 270} and width is not None and height is not None:
        width, height = height, width

    duration = None
    creation_time = None

    format_section = payload.get("format")
    if isinstance(format_section, dict):
        duration = _parse_float(format_section.get("duration"))
        creation_time = _parse_string(_get_nested(format_section, "tags", "creation_time"))

    if duration is None and isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            duration = _parse_float(stream.get("duration"))
            if duration is not None:
                break

    if creation_time is None and isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            creation_time = _parse_string(_get_nested(stream, "tags", "creation_time"))
            if creation_time is not None:
                break

    captured_at = _parse_iso_datetime(creation_time)
    duration_ms = _seconds_to_ms(duration)

    return MetadataResult(
        captured_at=captured_at,
        duration_ms=duration_ms,
        width=width,
        height=height,
    )


def _extract_exiftool(path: Path, exiftool_path: str) -> MetadataResult:
    output = _run_command(
        [
            exiftool_path,
            "-j",
            "-n",
            "-api",
            "LargeFileSupport=1",
            str(path),
        ]
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise MetadataParseError("exiftool output was not valid JSON") from exc
    return parse_exiftool_payload(payload)


def _extract_ffprobe(path: Path, ffprobe_path: str) -> MetadataResult:
    output = _run_command(
        [
            ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_entries",
            "stream=width,height,rotation:format=duration:format_tags=creation_time",
            str(path),
        ]
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise MetadataParseError("ffprobe output was not valid JSON") from exc
    return parse_ffprobe_payload(payload)


def _run_command(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise MetadataToolError(f"command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        message = f"command failed: {args[0]}"
        if stderr:
            message = f"{message}: {stderr}"
        raise MetadataToolError(message) from exc
    return completed.stdout


def _first_int(data: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = _parse_int(data.get(key))
        if value is not None:
            return value
    return None


def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _parse_string(data.get(key))
        if value is not None:
            return value
    return None


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _parse_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _parse_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_exif_datetime(value: str | None, offset: str | None) -> datetime | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    match = re.match(
        r"^(\d{4}:\d{2}:\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:\s?([+-]\d{2}:?\d{2}|Z))?$",
        raw,
    )
    if match:
        date_part, time_part, fraction, inline_offset = match.groups()
        dt = datetime.strptime(f"{date_part} {time_part}", "%Y:%m:%d %H:%M:%S")
        if fraction:
            micro = int(fraction.ljust(6, "0")[:6])
            dt = dt.replace(microsecond=micro)
        tzinfo = _parse_offset(inline_offset or offset)
        if tzinfo is None:
            tzinfo = timezone.utc
        return dt.replace(tzinfo=tzinfo)

    return _parse_iso_datetime(raw)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_offset(value: str | None) -> timezone | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw == "Z":
        return timezone.utc
    match = re.match(r"^([+-])(\d{2}):?(\d{2})$", raw)
    if match is None:
        return None
    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    if sign == "-":
        delta = -delta
    return timezone(delta)


def _seconds_to_ms(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(value * 1000))


T = TypeVar("T")


def _coalesce(*values: T | None) -> T | None:
    for value in values:
        if value is not None:
            return value
    return None


def _get_nested(data: dict[str, Any], *keys: str) -> object:
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
