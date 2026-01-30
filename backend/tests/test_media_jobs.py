import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import JobStatus, JobType
from app.db.models import Job
from app.media.jobs import (
    MediaJobFailure,
    RetryPolicy,
    is_retryable_media_error,
    media_job_status_payload,
    record_media_job_failure,
    retry_policy_for_job,
)
from app.media.metadata import MetadataNotFoundError, MetadataToolError
from app.media.thumbnails import ThumbnailToolError
from app.media.transcode import TranscodeToolError


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


class RetryPolicyTest(unittest.TestCase):
    def test_delay_seconds_exponential_with_cap(self) -> None:
        policy = RetryPolicy(
            max_attempts=3,
            base_delay_seconds=10,
            max_delay_seconds=25,
            backoff_factor=2.0,
        )
        self.assertEqual(policy.delay_seconds(1), 10)
        self.assertEqual(policy.delay_seconds(2), 20)
        self.assertEqual(policy.delay_seconds(3), 25)

    def test_delay_seconds_requires_positive_attempt(self) -> None:
        policy = RetryPolicy(
            max_attempts=3,
            base_delay_seconds=10,
            max_delay_seconds=25,
            backoff_factor=2.0,
        )
        with self.assertRaises(ValueError):
            policy.delay_seconds(0)


class MediaJobRetryPolicyTest(unittest.TestCase):
    def test_retry_policy_for_media_job(self) -> None:
        policy = retry_policy_for_job(JobType.metadata)
        self.assertIsNotNone(policy)

    def test_retry_policy_for_unsupported_job(self) -> None:
        with self.assertRaises(ValueError):
            retry_policy_for_job(JobType.scan)


class MediaJobRetryableErrorTest(unittest.TestCase):
    def test_retryable_and_non_retryable_errors(self) -> None:
        self.assertTrue(is_retryable_media_error(MetadataToolError("missing")))
        self.assertTrue(is_retryable_media_error(ThumbnailToolError("missing")))
        self.assertTrue(is_retryable_media_error(TranscodeToolError("missing")))
        self.assertFalse(is_retryable_media_error(MetadataNotFoundError("missing")))
        self.assertFalse(is_retryable_media_error(ValueError("nope")))


class MediaJobFailureRecordingTest(unittest.TestCase):
    def test_record_failure_schedules_retry(self) -> None:
        session, engine = _create_session()
        try:
            job = Job(
                type=JobType.metadata,
                status=JobStatus.running,
                payload={"asset_id": "asset-1"},
            )
            session.add(job)
            session.flush()

            policy = RetryPolicy(
                max_attempts=3,
                base_delay_seconds=30,
                max_delay_seconds=120,
                backoff_factor=2.0,
            )
            now = datetime(2025, 1, 1, tzinfo=timezone.utc)

            failure = record_media_job_failure(
                job,
                MetadataToolError("exiftool missing"),
                policy=policy,
                now_fn=lambda: now,
            )

            self.assertIsInstance(failure, MediaJobFailure)
            self.assertEqual(job.status, JobStatus.queued)
            self.assertEqual(job.payload.get("attempts"), 1)
            self.assertEqual(job.payload.get("max_attempts"), 3)
            self.assertEqual(job.payload.get("retry_after_seconds"), 30)
            self.assertEqual(
                job.payload.get("next_retry_at"),
                (now + timedelta(seconds=30)).isoformat(),
            )
            error = job.payload.get("error")
            self.assertEqual(error.get("type"), "MetadataToolError")
            self.assertTrue(error.get("retryable"))
            self.assertIn("exiftool", error.get("hint", ""))
            self.assertEqual(failure.retry_after_seconds, 30)
            self.assertEqual(failure.next_retry_at, now + timedelta(seconds=30))
        finally:
            session.close()
            engine.dispose()

    def test_record_failure_marks_failed_when_non_retryable(self) -> None:
        session, engine = _create_session()
        try:
            job = Job(
                type=JobType.metadata,
                status=JobStatus.running,
                payload={"asset_id": "asset-2", "attempts": 1},
            )
            session.add(job)
            session.flush()

            policy = RetryPolicy(
                max_attempts=3,
                base_delay_seconds=10,
                max_delay_seconds=60,
                backoff_factor=2.0,
            )
            now = datetime(2025, 1, 2, tzinfo=timezone.utc)

            record_media_job_failure(
                job,
                MetadataNotFoundError("asset missing"),
                policy=policy,
                now_fn=lambda: now,
            )

            self.assertEqual(job.status, JobStatus.failed)
            self.assertEqual(job.payload.get("attempts"), 2)
            self.assertIsNone(job.payload.get("next_retry_at"))
            error = job.payload.get("error")
            self.assertFalse(error.get("retryable"))
        finally:
            session.close()
            engine.dispose()

    def test_record_failure_marks_failed_when_attempts_exhausted(self) -> None:
        session, engine = _create_session()
        try:
            job = Job(
                type=JobType.thumb,
                status=JobStatus.running,
                payload={"asset_id": "asset-3", "attempts": 2},
            )
            session.add(job)
            session.flush()

            policy = RetryPolicy(
                max_attempts=2,
                base_delay_seconds=10,
                max_delay_seconds=60,
                backoff_factor=2.0,
            )
            now = datetime(2025, 1, 3, tzinfo=timezone.utc)

            record_media_job_failure(
                job,
                ThumbnailToolError("pyvips missing"),
                policy=policy,
                now_fn=lambda: now,
            )

            self.assertEqual(job.status, JobStatus.failed)
            self.assertEqual(job.payload.get("attempts"), 3)
            self.assertIsNone(job.payload.get("next_retry_at"))
        finally:
            session.close()
            engine.dispose()

    def test_status_payload_includes_error_context(self) -> None:
        session, engine = _create_session()
        try:
            job = Job(
                type=JobType.transcode,
                status=JobStatus.failed,
                payload={
                    "asset_id": "asset-4",
                    "attempts": 2,
                    "max_attempts": 2,
                    "retry_after_seconds": None,
                    "next_retry_at": None,
                    "failed_at": "2025-01-04T00:00:00+00:00",
                    "error": {"type": "TranscodeToolError", "message": "ffmpeg"},
                },
            )
            session.add(job)
            session.flush()

            payload = media_job_status_payload(job)

            self.assertEqual(payload.get("status"), "failed")
            self.assertEqual(payload.get("asset_id"), "asset-4")
            self.assertEqual(payload.get("attempts"), 2)
            self.assertEqual(payload.get("error").get("type"), "TranscodeToolError")
        finally:
            session.close()
            engine.dispose()
