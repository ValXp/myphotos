from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import logging
import time
from typing import Callable, Iterable, Mapping, Sequence

from sqlalchemy.orm import Session, sessionmaker

from app.config import Config, load_config
from app.db.enums import JobStatus, JobType
from app.db.models import AssetVariant, Job as JobRecord
from app.db.session import create_engine_from_config, create_session_factory
from app.media.jobs import record_media_job_failure, retry_policy_for_job
from app.media.metadata import MetadataResult, run_metadata_job
from app.media.thumbnails import run_thumbnail_job
from app.media.transcode import run_transcode_job
from app.observability import configure_logging
from app.queue import (
    Job as QueueJob,
    Queue,
    RedisQueueBackend,
    UnknownJobError,
    create_redis_client,
)

logger = logging.getLogger("app.workers.media")

MediaHandler = Callable[[Session, str], object]
SleepFn = Callable[[float], None]
NowFn = Callable[[], datetime]


class MediaWorker:
    def __init__(
        self,
        queue: Queue,
        session_factory: sessionmaker[Session],
        config: Config,
        *,
        metadata_handler: MediaHandler | None = None,
        thumbnail_handler: MediaHandler | None = None,
        transcode_handler: MediaHandler | None = None,
        vips_module: object | None = None,
        poster_extractor: object | None = None,
        transcode_func: object | None = None,
        live_video_generator: object | None = None,
        ffmpeg_path: str = "ffmpeg",
        exiftool_path: str = "exiftool",
        ffprobe_path: str = "ffprobe",
        sleep_fn: SleepFn | None = None,
        now_fn: NowFn | None = None,
    ) -> None:
        self._queue = queue
        self._session_factory = session_factory
        self._config = config
        self._sleep = sleep_fn or time.sleep
        self._now = now_fn or _utcnow
        self._metadata_handler = metadata_handler or (
            lambda session, asset_id: run_metadata_job(
                session,
                asset_id,
                exiftool_path=exiftool_path,
                ffprobe_path=ffprobe_path,
            )
        )
        self._thumbnail_handler = thumbnail_handler or (
            lambda session, asset_id: run_thumbnail_job(
                session,
                asset_id,
                derived_root=self._config.paths.derived,
                vips_module=vips_module,
                ffmpeg_path=ffmpeg_path,
                poster_extractor=poster_extractor,
            )
        )
        self._transcode_handler = transcode_handler or (
            lambda session, asset_id: run_transcode_job(
                session,
                asset_id,
                derived_root=self._config.paths.derived,
                config=self._config,
                ffmpeg_path=ffmpeg_path,
                transcode_func=transcode_func,
                live_video_generator=live_video_generator,
            )
        )
        self._register_handlers()

    def _register_handlers(self) -> None:
        self._queue.register(JobType.metadata.value, self._handle_metadata)
        self._queue.register(JobType.thumb.value, self._handle_thumbnail)
        self._queue.register(JobType.transcode.value, self._handle_transcode)

    def run_once(self, *, timeout: int | None = None) -> bool:
        try:
            return self._queue.process_next(timeout)
        except UnknownJobError:
            logger.exception("media_worker.unknown_job")
            return True
        except Exception:
            logger.exception("media_worker.job_failed")
            return True

    def run_forever(self, *, poll_timeout: int = 5) -> None:
        while True:
            try:
                self._queue.process_next(timeout=poll_timeout)
            except UnknownJobError:
                logger.exception("media_worker.unknown_job")
            except Exception:
                logger.exception("media_worker.job_failed")

    def _handle_metadata(self, job: QueueJob) -> None:
        self._process_job(job, JobType.metadata, self._metadata_handler)

    def _handle_thumbnail(self, job: QueueJob) -> None:
        self._process_job(job, JobType.thumb, self._thumbnail_handler)

    def _handle_transcode(self, job: QueueJob) -> None:
        self._process_job(job, JobType.transcode, self._transcode_handler)

    def _process_job(self, job: QueueJob, job_type: JobType, handler: MediaHandler) -> None:
        if job.id is None or not job.id.strip():
            raise ValueError("queue job id is required for media worker")
        session = self._session_factory()
        db_job = None
        try:
            db_job = self._get_or_create_job(session, job, job_type)
            payload = _merge_payload(db_job.payload, job.payload)
            asset_id = _asset_id_from_payload(payload)
            if asset_id is None:
                raise ValueError("asset_id is required for media jobs")
            started_at = self._now()
            payload["asset_id"] = asset_id
            payload["started_at"] = started_at.isoformat()
            db_job.status = JobStatus.running
            db_job.payload = payload
            session.add(db_job)
            session.commit()

            result = handler(session, asset_id)

            finished_at = self._now()
            payload = dict(db_job.payload or {})
            payload["finished_at"] = finished_at.isoformat()
            payload.update(_summarize_result(job_type, result))
            db_job.status = JobStatus.done
            db_job.payload = payload
            session.add(db_job)
            session.commit()
        except Exception as exc:
            session.rollback()
            if db_job is None:
                raise
            failure = record_media_job_failure(
                db_job,
                exc,
                policy=retry_policy_for_job(job_type),
                now_fn=self._now,
            )
            payload = dict(db_job.payload or {})
            if payload.get("failed_at") and not payload.get("finished_at"):
                payload["finished_at"] = payload.get("failed_at")
                db_job.payload = payload
            session.add(db_job)
            session.commit()
            logger.exception(
                "media_worker.job_error",
                extra={
                    "job_type": job_type.value,
                    "asset_id": failure.asset_id,
                    "retryable": failure.retryable,
                    "attempts": failure.attempts,
                    "max_attempts": failure.max_attempts,
                },
            )
            if db_job.status == JobStatus.queued:
                retry_after = _int_from_payload(db_job.payload.get("retry_after_seconds"))
                if retry_after is not None and retry_after > 0:
                    self._sleep(retry_after)
                self._queue.enqueue(
                    QueueJob(
                        name=job_type.value,
                        payload=dict(db_job.payload or {}),
                        id=db_job.id,
                    )
                )
            raise
        finally:
            session.close()

    def _get_or_create_job(
        self, session: Session, job: QueueJob, job_type: JobType
    ) -> JobRecord:
        if job.id is None:
            raise ValueError("job id is required")
        record = session.get(JobRecord, job.id)
        if record is None:
            record = JobRecord(
                id=job.id,
                type=job_type,
                status=JobStatus.queued,
                payload={},
            )
            session.add(record)
            return record
        record.type = job_type
        return record


def _merge_payload(
    existing: Mapping[str, object] | None, incoming: Mapping[str, object]
) -> dict[str, object]:
    payload = dict(existing or {})
    payload.update(incoming)
    return payload


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


def _summarize_result(job_type: JobType, result: object) -> dict[str, object]:
    if job_type == JobType.metadata and isinstance(result, MetadataResult):
        return {"metadata": _serialize_metadata(result)}
    if job_type in {JobType.thumb, JobType.transcode}:
        return _serialize_variants(result)
    return {}


def _serialize_metadata(result: MetadataResult) -> dict[str, object]:
    payload = asdict(result)
    captured_at = payload.get("captured_at")
    if isinstance(captured_at, datetime):
        payload["captured_at"] = captured_at.isoformat()
    return payload


def _serialize_variants(result: object) -> dict[str, object]:
    if not isinstance(result, Iterable) or isinstance(result, (str, bytes, dict)):
        return {}
    variants: list[dict[str, object]] = []
    for item in result:
        if isinstance(item, AssetVariant):
            kind = item.kind.value if hasattr(item.kind, "value") else str(item.kind)
            variants.append({"kind": kind, "profile": item.profile})
    if not variants:
        return {}
    return {"variant_count": len(variants), "variants": variants}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Media worker for myphotos")
    parser.add_argument("--once", action="store_true", help="Process a single job and exit")
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=5,
        help="Seconds to block waiting for jobs in the queue",
    )
    args = parser.parse_args(argv)

    config = load_config()
    configure_logging(config.app.log_level)
    engine = create_engine_from_config(config)
    session_factory = create_session_factory(engine)
    queue = Queue(RedisQueueBackend(create_redis_client(config.redis)))
    worker = MediaWorker(queue, session_factory, config)

    if args.once:
        worker.run_once()
        engine.dispose()
        return 0

    try:
        worker.run_forever(poll_timeout=args.poll_timeout)
    except KeyboardInterrupt:
        logger.info("media_worker.shutdown")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
