from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
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
