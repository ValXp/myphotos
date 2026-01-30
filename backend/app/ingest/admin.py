from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import JobStatus, JobType
from app.db.models import Job
from app.ingest.jobs import enqueue_scan_jobs
from app.ingest.scan import ScanStats
from app.observability import job_context
from app.queue import Queue

DEFAULT_LARGE_SCAN_THRESHOLD = 10000
DEFAULT_SCAN_BACKOFF_SECONDS = 300

logger = logging.getLogger("app.jobs.scan")


@dataclass(frozen=True)
class ScanBackoffPolicy:
    large_scan_threshold: int = DEFAULT_LARGE_SCAN_THRESHOLD
    backoff_seconds: int = DEFAULT_SCAN_BACKOFF_SECONDS

    def backoff_until(self, stats: ScanStats, finished_at: datetime) -> datetime | None:
        if stats.scanned < self.large_scan_threshold:
            return None
        return finished_at + timedelta(seconds=self.backoff_seconds)


class ScanError(RuntimeError):
    pass


class ScanInProgressError(ScanError):
    def __init__(self, job: Job) -> None:
        super().__init__("scan already running")
        self.job = job


class ScanBackoffError(ScanError):
    def __init__(self, backoff_until: datetime, retry_after_seconds: int) -> None:
        super().__init__("scan backoff active")
        self.backoff_until = backoff_until
        self.retry_after_seconds = retry_after_seconds


class ScanFailedError(ScanError):
    def __init__(self, job: Job, message: str) -> None:
        super().__init__(message)
        self.job = job


def latest_scan_job(session: Session) -> Job | None:
    return session.execute(
        select(Job).where(Job.type == JobType.scan).order_by(Job.created_at.desc())
    ).scalar_one_or_none()


def scan_status_payload(job: Job | None) -> dict[str, object]:
    if job is None:
        return {"status": "idle"}
    payload = job.payload or {}
    return {
        "status": job.status.value,
        "job_id": job.id,
        "roots": payload.get("roots", []),
        "stats": payload.get("stats"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "backoff_until": payload.get("backoff_until"),
        "error": payload.get("error"),
    }


def start_scan(
    session: Session,
    roots: Iterable[str | Path],
    queue: Queue,
    policy: ScanBackoffPolicy,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> Job:
    active_job = _active_scan_job(session)
    if active_job is not None:
        raise ScanInProgressError(active_job)

    now = now_fn or _utcnow
    backoff_until = _scan_backoff_until(session, policy, now)
    if backoff_until is not None:
        retry_after = max(1, int((backoff_until - now()).total_seconds()))
        raise ScanBackoffError(backoff_until, retry_after)

    roots_list = _normalize_roots(roots)
    started_at = now()
    job = Job(
        type=JobType.scan,
        status=JobStatus.running,
        payload={
            "roots": roots_list,
            "started_at": started_at.isoformat(),
        },
    )
    session.add(job)
    session.commit()

    with job_context(job.id):
        logger.info(
            "job.start",
            extra={"job_type": job.type.value, "roots": roots_list},
        )

    try:
        stats = enqueue_scan_jobs(session, roots_list, queue)
        finished_at = now()
        backoff_expiry = policy.backoff_until(stats, finished_at)
        job.status = JobStatus.done
        job.payload = {
            "roots": roots_list,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "stats": _serialize_stats(stats),
            "backoff_until": backoff_expiry.isoformat() if backoff_expiry else None,
        }
        session.add(job)
        session.commit()
        with job_context(job.id):
            logger.info(
                "job.complete",
                extra={
                    "job_type": job.type.value,
                    "stats": _serialize_stats(stats),
                },
            )
        return job
    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        finished_at = now()
        job.status = JobStatus.failed
        job.payload = {
            "roots": roots_list,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": str(exc),
        }
        session.add(job)
        session.commit()
        with job_context(job.id):
            logger.exception(
                "job.error",
                extra={"job_type": job.type.value, "error": str(exc)},
            )
        raise ScanFailedError(job, str(exc)) from exc


def _active_scan_job(session: Session) -> Job | None:
    return session.execute(
        select(Job)
        .where(
            Job.type == JobType.scan,
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
        .order_by(Job.created_at.desc())
    ).scalar_one_or_none()


def _scan_backoff_until(
    session: Session,
    policy: ScanBackoffPolicy,
    now_fn: Callable[[], datetime],
) -> datetime | None:
    last_job = session.execute(
        select(Job)
        .where(Job.type == JobType.scan, Job.status == JobStatus.done)
        .order_by(Job.created_at.desc())
    ).scalar_one_or_none()
    if last_job is None:
        return None
    payload = last_job.payload or {}
    stats = _parse_stats(payload.get("stats"))
    finished_at = _parse_datetime(payload.get("finished_at"))
    if stats is None or finished_at is None:
        return None
    backoff_until = policy.backoff_until(stats, finished_at)
    if backoff_until is None:
        return None
    if now_fn() < backoff_until:
        return backoff_until
    return None


def _normalize_roots(roots: Iterable[str | Path]) -> list[str]:
    seen: set[Path] = set()
    normalized: list[str] = []
    for root in roots:
        path = Path(root).expanduser().resolve(strict=False)
        if path in seen:
            continue
        seen.add(path)
        normalized.append(str(path))
    return normalized


def _serialize_stats(stats: ScanStats) -> dict[str, object]:
    return {
        "scanned": stats.scanned,
        "supported": stats.supported,
        "created": stats.created,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "errors": list(stats.errors),
    }


def _parse_stats(data: object) -> ScanStats | None:
    if not isinstance(data, dict):
        return None
    errors = data.get("errors")
    if errors is None:
        error_list: list[str] = []
    elif isinstance(errors, list) and all(isinstance(item, str) for item in errors):
        error_list = list(errors)
    else:
        return None
    try:
        return ScanStats(
            scanned=int(data.get("scanned", 0)),
            supported=int(data.get("supported", 0)),
            created=int(data.get("created", 0)),
            updated=int(data.get("updated", 0)),
            unchanged=int(data.get("unchanged", 0)),
            errors=error_list,
        )
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
