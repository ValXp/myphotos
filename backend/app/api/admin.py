from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_config,
    get_db,
    get_queue,
    get_scan_backoff,
    require_owner_session,
)
from app.auth.sessions import Session as OwnerSession
from app.config import Config
from app.db.enums import JobStatus, JobType
from app.db.models import Asset, Job
from app.ingest.admin import (
    ScanBackoffError,
    ScanBackoffPolicy,
    ScanFailedError,
    ScanInProgressError,
    latest_scan_job,
    scan_status_payload,
    start_scan,
)
from app.queue import Queue

router = APIRouter(prefix="/admin/index")


@router.post("/scan")
def run_scan(
    response: Response,
    path: list[str] | None = Query(default=None),
    _: OwnerSession = Depends(require_owner_session),
    config: Config = Depends(get_config),
    db: Session = Depends(get_db),
    queue: Queue = Depends(get_queue),
    policy: ScanBackoffPolicy = Depends(get_scan_backoff),
) -> dict[str, object]:
    roots = _resolve_roots(config, path)
    try:
        job = start_scan(db, roots, queue, policy)
    except ScanInProgressError as exc:
        response.status_code = 409
        return scan_status_payload(exc.job)
    except ScanBackoffError as exc:
        response.status_code = 429
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return {
            "status": "backoff",
            "retry_after_seconds": exc.retry_after_seconds,
            "backoff_until": exc.backoff_until.isoformat(),
        }
    except ScanFailedError as exc:
        response.status_code = 500
        return scan_status_payload(exc.job)
    return scan_status_payload(job)


@router.get("/status")
def scan_status(
    _: OwnerSession = Depends(require_owner_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    job = latest_scan_job(db)
    return scan_status_payload(job)


@router.get("/overview")
def index_overview(
    _: OwnerSession = Depends(require_owner_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Lightweight admin status endpoint for UI polling.

    Returns scan status + counts of assets and jobs by type/status.
    """

    scan_job = latest_scan_job(db)
    scan = scan_status_payload(scan_job)

    asset_count = (
        db.execute(select(func.count()).select_from(Asset).where(Asset.gone.is_(False)))
        .scalar_one()
    )

    # Job counts.
    rows = db.execute(
        select(Job.type, Job.status, func.count())
        .where(Job.type.in_([JobType.metadata, JobType.thumb, JobType.transcode]))
        .group_by(Job.type, Job.status)
    ).all()

    counts: dict[str, dict[str, int]] = {}
    for job_type, job_status, count in rows:
        type_key = job_type.value if job_type else "unknown"
        status_key = job_status.value if job_status else "unknown"
        counts.setdefault(type_key, {})[status_key] = int(count)

    def get_count(job_type: str, status: JobStatus) -> int:
        return counts.get(job_type, {}).get(status.value, 0)

    job_summary = {
        "metadata": {
            "queued": get_count("metadata", JobStatus.queued),
            "running": get_count("metadata", JobStatus.running),
            "done": get_count("metadata", JobStatus.done),
            "failed": get_count("metadata", JobStatus.failed),
        },
        "thumb": {
            "queued": get_count("thumb", JobStatus.queued),
            "running": get_count("thumb", JobStatus.running),
            "done": get_count("thumb", JobStatus.done),
            "failed": get_count("thumb", JobStatus.failed),
        },
        "transcode": {
            "queued": get_count("transcode", JobStatus.queued),
            "running": get_count("transcode", JobStatus.running),
            "done": get_count("transcode", JobStatus.done),
            "failed": get_count("transcode", JobStatus.failed),
        },
    }

    active_jobs = (
        job_summary["metadata"]["queued"]
        + job_summary["metadata"]["running"]
        + job_summary["thumb"]["queued"]
        + job_summary["thumb"]["running"]
        + job_summary["transcode"]["queued"]
        + job_summary["transcode"]["running"]
    )

    return {
        "scan": scan,
        "assets": {"count": int(asset_count)},
        "jobs": job_summary,
        "active_jobs": int(active_jobs),
    }


def _resolve_roots(config: Config, paths: list[str] | None) -> list[Path]:
    if not paths:
        return [config.paths.originals]
    roots: list[Path] = []
    for value in paths:
        root = Path(value)
        if not root.is_absolute():
            root = config.paths.originals / root
        roots.append(root)
    return roots
