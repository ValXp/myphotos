from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from app.db.enums import JobStatus, JobType
from app.db.models import Job
from app.media.metadata import MetadataNotFoundError, MetadataToolError
from app.media.thumbnails import ThumbnailNotFoundError, ThumbnailToolError
from app.media.transcode import TranscodeNotFoundError, TranscodeToolError

MEDIA_JOB_TYPES = (JobType.metadata, JobType.thumb, JobType.transcode)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int
    backoff_factor: float = 2.0

    def delay_seconds(self, attempt: int) -> int:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        delay = self.base_delay_seconds * (self.backoff_factor ** (attempt - 1))
        return min(int(round(delay)), self.max_delay_seconds)


DEFAULT_MEDIA_RETRY_POLICIES: Mapping[JobType, RetryPolicy] = {
    JobType.metadata: RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=900),
    JobType.thumb: RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=900),
    JobType.transcode: RetryPolicy(max_attempts=2, base_delay_seconds=60, max_delay_seconds=1800),
}


@dataclass(frozen=True)
class MediaJobFailure:
    job_id: str
    job_type: JobType
    asset_id: str | None
    attempts: int
    max_attempts: int
    retryable: bool
    retry_after_seconds: int | None
    next_retry_at: datetime | None
    failed_at: datetime
    error_type: str
    message: str
    hint: str | None

    def as_report(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "type": self.job_type.value,
            "asset_id": self.asset_id,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "failed_at": self.failed_at.isoformat(),
            "error": {
                "type": self.error_type,
                "message": self.message,
                "hint": self.hint,
                "retryable": self.retryable,
            },
        }


NON_RETRYABLE_ERRORS = (
    MetadataNotFoundError,
    ThumbnailNotFoundError,
    TranscodeNotFoundError,
)

RETRYABLE_ERRORS = (
    MetadataToolError,
    ThumbnailToolError,
    TranscodeToolError,
)


def retry_policy_for_job(job_type: JobType) -> RetryPolicy:
    policy = DEFAULT_MEDIA_RETRY_POLICIES.get(job_type)
    if policy is None:
        raise ValueError(f"unsupported media job type: {job_type}")
    return policy


def is_retryable_media_error(error: Exception) -> bool:
    if isinstance(error, NON_RETRYABLE_ERRORS):
        return False
    return isinstance(error, RETRYABLE_ERRORS)


def media_error_hint(error: Exception) -> str | None:
    if isinstance(error, MetadataToolError):
        return "Ensure exiftool and ffprobe are installed and on PATH."
    if isinstance(error, ThumbnailToolError):
        return "Ensure pyvips is installed and ffmpeg is available for video posters."
    if isinstance(error, TranscodeToolError):
        return "Ensure ffmpeg is installed and supports libx264 and AAC."
    return None


def record_media_job_failure(
    job: Job,
    error: Exception,
    *,
    policy: RetryPolicy,
    now_fn: Callable[[], datetime] | None = None,
) -> MediaJobFailure:
    now = (now_fn or _utcnow)()
    attempts = _next_attempts(job.payload or {})
    asset_id = _asset_id_from_payload(job.payload or {})
    retryable_error = is_retryable_media_error(error)
    should_retry = retryable_error and attempts < policy.max_attempts
    retry_after_seconds = None
    next_retry_at = None
    if should_retry:
        retry_after_seconds = policy.delay_seconds(attempts)
        next_retry_at = now + timedelta(seconds=retry_after_seconds)

    failure = MediaJobFailure(
        job_id=job.id,
        job_type=job.type,
        asset_id=asset_id,
        attempts=attempts,
        max_attempts=policy.max_attempts,
        retryable=should_retry,
        retry_after_seconds=retry_after_seconds,
        next_retry_at=next_retry_at,
        failed_at=now,
        error_type=type(error).__name__,
        message=str(error),
        hint=media_error_hint(error),
    )

    payload = dict(job.payload or {})
    if asset_id is not None:
        payload["asset_id"] = asset_id
    payload.update(
        {
            "attempts": attempts,
            "max_attempts": policy.max_attempts,
            "failed_at": now.isoformat(),
            "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
            "retry_after_seconds": retry_after_seconds,
            "error": {
                "type": failure.error_type,
                "message": failure.message,
                "hint": failure.hint,
                "retryable": failure.retryable,
            },
        }
    )

    job.status = JobStatus.queued if should_retry else JobStatus.failed
    job.payload = payload

    return failure


def media_job_status_payload(job: Job) -> dict[str, object]:
    payload = job.payload or {}
    return {
        "status": job.status.value,
        "job_id": job.id,
        "type": job.type.value,
        "asset_id": _asset_id_from_payload(payload),
        "attempts": _int_from_payload(payload.get("attempts")),
        "max_attempts": _int_from_payload(payload.get("max_attempts")),
        "retry_after_seconds": _int_from_payload(payload.get("retry_after_seconds")),
        "next_retry_at": payload.get("next_retry_at"),
        "failed_at": payload.get("failed_at"),
        "error": payload.get("error"),
    }


def _asset_id_from_payload(payload: Mapping[str, object]) -> str | None:
    value = payload.get("asset_id")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _int_from_payload(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _next_attempts(payload: Mapping[str, object]) -> int:
    attempts = _int_from_payload(payload.get("attempts"))
    if attempts is None or attempts < 0:
        attempts = 0
    return attempts + 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
