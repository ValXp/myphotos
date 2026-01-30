from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import uuid
import zipfile
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.db.enums import JobStatus, JobType
from app.db.models import AlbumItem, AlbumZip, Asset, Job

ZIP_DIRNAME = "album_zips"


class ZipError(RuntimeError):
    pass


class ZipInProgressError(ZipError):
    def __init__(self, job: Job) -> None:
        super().__init__("zip job already running")
        self.job = job


class ZipFailedError(ZipError):
    def __init__(self, job: Job, message: str) -> None:
        super().__init__(message)
        self.job = job


@dataclass(frozen=True)
class ZipEntry:
    source_path: Path
    arcname: str


def start_album_zip_job(
    session: Session,
    album_id: str,
    config: Config,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> Job:
    active_job = _active_zip_job(session, album_id)
    if active_job is not None:
        raise ZipInProgressError(active_job)

    now = now_fn or _utcnow
    started_at = now()
    job = Job(
        type=JobType.zip,
        status=JobStatus.running,
        payload={"album_id": album_id, "started_at": started_at.isoformat()},
    )
    session.add(job)
    session.commit()

    try:
        assets = _album_assets(session, album_id)
        zip_rel_path = _zip_relative_path(album_id)
        zip_full_path = _resolve_zip_path(zip_rel_path, config.paths.derived)
        zip_bytes = create_album_zip(
            assets, config.paths.originals, zip_full_path, temp_root=config.paths.temp
        )
        finished_at = now()
        _upsert_album_zip(session, album_id, zip_rel_path, finished_at)
        payload = dict(job.payload or {})
        payload.update(
            {
                "album_id": album_id,
                "finished_at": finished_at.isoformat(),
                "zip_path": str(zip_rel_path),
                "zip_bytes": zip_bytes,
                "asset_count": len(assets),
            }
        )
        job.status = JobStatus.done
        job.payload = payload
        session.add(job)
        session.commit()
        return job
    except Exception as exc:
        session.rollback()
        finished_at = now()
        payload = dict(job.payload or {})
        payload.update(
            {
                "album_id": album_id,
                "finished_at": finished_at.isoformat(),
                "error": str(exc),
            }
        )
        job.status = JobStatus.failed
        job.payload = payload
        session.add(job)
        session.commit()
        raise ZipFailedError(job, str(exc)) from exc


def latest_zip_job(session: Session, album_id: str) -> Job | None:
    jobs = session.execute(
        select(Job).where(Job.type == JobType.zip).order_by(Job.created_at.desc())
    ).scalars()
    for job in jobs:
        if _job_album_id(job) == album_id:
            return job
    return None


def album_zip_record(session: Session, album_id: str) -> AlbumZip | None:
    return (
        session.query(AlbumZip)
        .filter(AlbumZip.album_id == album_id)
        .one_or_none()
    )


def zip_status_payload(
    job: Job | None,
    album_zip: AlbumZip | None,
    album_id: str,
) -> dict[str, object]:
    status = _zip_status(job, album_zip)
    payload = job.payload or {} if job is not None else {}
    return {
        "status": status,
        "album_id": album_id,
        "job_id": job.id if job is not None else None,
        "asset_count": _int_from_payload(payload.get("asset_count")),
        "zip_bytes": _int_from_payload(payload.get("zip_bytes")),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "created_at": _isoformat(album_zip.created_at) if album_zip else None,
        "invalidated_at": _isoformat(album_zip.invalidated_at) if album_zip else None,
        "download_url": _download_url(album_zip, album_id),
        "error": payload.get("error"),
    }


def create_album_zip(
    assets: list[Asset],
    originals_root: Path,
    output_path: Path,
    *,
    temp_root: Path,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_path = temp_root / f"{output_path.stem}-{uuid.uuid4().hex}.zip.tmp"
    entries = _build_zip_entries(assets, originals_root)
    try:
        with zipfile.ZipFile(
            temp_path, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for entry in entries:
                archive.write(entry.source_path, arcname=entry.arcname)
        temp_path.replace(output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return output_path.stat().st_size


def _active_zip_job(session: Session, album_id: str) -> Job | None:
    jobs = session.execute(
        select(Job)
        .where(
            Job.type == JobType.zip,
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
        .order_by(Job.created_at.desc())
    ).scalars()
    for job in jobs:
        if _job_album_id(job) == album_id:
            return job
    return None


def _job_album_id(job: Job) -> str | None:
    payload = job.payload or {}
    value = payload.get("album_id")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _album_assets(session: Session, album_id: str) -> list[Asset]:
    rows = (
        session.query(AlbumItem, Asset)
        .join(Asset, AlbumItem.asset_id == Asset.id)
        .filter(AlbumItem.album_id == album_id)
        .order_by(AlbumItem.order_index.asc(), AlbumItem.asset_id.asc())
        .all()
    )
    return [asset for _, asset in rows]


def _build_zip_entries(assets: list[Asset], originals_root: Path) -> list[ZipEntry]:
    entries: list[ZipEntry] = []
    seen: dict[str, int] = {}
    for asset in assets:
        source_path = _resolve_original_path(asset.original_path, originals_root)
        arcname = _zip_entry_name(source_path, originals_root)
        arcname = _dedupe_name(arcname, seen)
        entries.append(ZipEntry(source_path=source_path, arcname=arcname))
    return entries


def _resolve_original_path(path: str, originals_root: Path) -> Path:
    original_path = Path(path)
    if not original_path.is_absolute():
        original_path = originals_root / original_path
    return original_path


def _zip_entry_name(path: Path, originals_root: Path) -> str:
    try:
        relative = path.relative_to(originals_root)
        name = relative.as_posix()
    except ValueError:
        name = path.name
    return name or path.name


def _dedupe_name(name: str, seen: dict[str, int]) -> str:
    if name not in seen:
        seen[name] = 1
        return name
    seen[name] += 1
    posix = PurePosixPath(name)
    suffix = posix.suffix
    stem = posix.stem
    parent = posix.parent
    new_name = f"{stem}-{seen[name]}{suffix}"
    if str(parent) != ".":
        return str(parent / new_name)
    return new_name


def _zip_relative_path(album_id: str) -> Path:
    return Path(ZIP_DIRNAME) / f"{album_id}.zip"


def _resolve_zip_path(path: Path, derived_root: Path) -> Path:
    if path.is_absolute():
        return path
    return derived_root / path


def _upsert_album_zip(
    session: Session, album_id: str, path: Path, created_at: datetime
) -> AlbumZip:
    record = album_zip_record(session, album_id)
    if record is None:
        record = AlbumZip(album_id=album_id, path=str(path), created_at=created_at)
        session.add(record)
    else:
        record.path = str(path)
        record.created_at = created_at
        record.invalidated_at = None
        session.add(record)
    return record


def _zip_status(job: Job | None, album_zip: AlbumZip | None) -> str:
    if job is not None:
        return job.status.value
    if album_zip is not None and album_zip.invalidated_at is None:
        return JobStatus.done.value
    return "idle"


def _download_url(album_zip: AlbumZip | None, album_id: str) -> str | None:
    if album_zip is None or album_zip.invalidated_at is not None:
        return None
    return f"/albums/{album_id}/zip/download"


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _int_from_payload(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
