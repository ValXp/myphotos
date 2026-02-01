import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import (
    AppConfig,
    Config,
    DatabaseConfig,
    PathsConfig,
    RedisConfig,
    SessionConfig,
    WebAuthnConfig,
)
from app.db.base import Base
from app.db.enums import AssetVariantKind, AssetType, JobStatus, JobType
from app.db.models import Asset, AssetVariant, Job as JobRecord
from app.media.metadata import MetadataNotFoundError, MetadataResult
from app.queue import InMemoryQueueBackend, Job, Queue, UnknownJobError
from workers import media_worker
from workers.media_worker import (
    MediaWorker,
    _asset_id_from_payload,
    _int_from_payload,
    _merge_payload,
    _serialize_metadata,
    _serialize_variants,
    _summarize_result,
)


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    return session_factory, engine


def _test_config(root: Path) -> Config:
    return Config(
        paths=PathsConfig(
            data_root=root,
            originals=root / "originals",
            derived=root / "derived",
            temp=root / "temp",
        ),
        database=DatabaseConfig(url="sqlite+pysqlite:///:memory:"),
        redis=RedisConfig(url="redis://localhost:6379/0"),
        webauthn=WebAuthnConfig(
            rp_id="localhost",
            rp_name="myphotos",
            origins=("http://localhost",),
        ),
        app=AppConfig(
            env="test",
            host="127.0.0.1",
            port=8000,
            log_level="INFO",
            trusted_proxy_ips=(),
            frontend_dist_dir=None,
        ),
        session=SessionConfig(
            ttl_seconds=3600,
            cookie_name="myphotos_session",
        ),
    )


class MediaWorkerHelpersTest(unittest.TestCase):
    def test_payload_helpers(self) -> None:
        merged = _merge_payload({"a": 1}, {"b": 2, "a": 3})
        self.assertEqual(merged, {"a": 3, "b": 2})

        self.assertIsNone(_asset_id_from_payload({}))
        self.assertIsNone(_asset_id_from_payload({"asset_id": ""}))
        self.assertEqual(_asset_id_from_payload({"asset_id": "asset-1"}), "asset-1")

        self.assertIsNone(_int_from_payload(True))
        self.assertIsNone(_int_from_payload("1"))
        self.assertEqual(_int_from_payload(3), 3)

    def test_result_serialization(self) -> None:
        captured_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        metadata = MetadataResult(width=100, height=200, captured_at=captured_at)
        payload = _serialize_metadata(metadata)
        self.assertEqual(payload.get("captured_at"), captured_at.isoformat())

        self.assertEqual(_serialize_variants(None), {})
        self.assertEqual(_serialize_variants("nope"), {})

        variants = [
            AssetVariant(
                asset_id="asset-1",
                kind=AssetVariantKind.thumb,
                profile="thumb_sm",
                path="/tmp/thumb_sm.jpg",
                bytes=123,
            )
        ]
        variants_payload = _serialize_variants(variants)
        self.assertEqual(variants_payload.get("variant_count"), 1)
        self.assertEqual(variants_payload.get("variants"), [{"kind": "thumb", "profile": "thumb_sm"}])

        self.assertEqual(
            _summarize_result(JobType.metadata, metadata),
            {"metadata": payload},
        )
        self.assertEqual(
            _summarize_result(JobType.thumb, variants),
            variants_payload,
        )
        self.assertEqual(_summarize_result(JobType.zip, {}), {})


class MediaWorkerUnitTest(unittest.TestCase):
    def test_run_once_catches_queue_errors(self) -> None:
        queue = MagicMock()
        queue.register = MagicMock()
        queue.process_next.side_effect = UnknownJobError("unknown")
        session_factory = MagicMock()
        config = SimpleNamespace(paths=SimpleNamespace(derived=Path("/tmp")))
        worker = MediaWorker(queue, session_factory, config)
        self.assertTrue(worker.run_once())

        queue.process_next.side_effect = RuntimeError("boom")
        self.assertTrue(worker.run_once())

    def test_process_job_requires_queue_job_id(self) -> None:
        queue = MagicMock()
        queue.register = MagicMock()
        session_factory = MagicMock()
        config = SimpleNamespace(paths=SimpleNamespace(derived=Path("/tmp")))
        worker = MediaWorker(queue, session_factory, config)

        with self.assertRaises(ValueError):
            worker._process_job(Job(name="metadata", payload={}, id=None), JobType.metadata, lambda *_: None)  # type: ignore[arg-type]

    def test_non_retryable_failure_marks_failed_and_does_not_reenqueue(self) -> None:
        session_factory, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config = _test_config(root)
                queue = Queue(InMemoryQueueBackend())

                with session_factory() as session:
                    asset = Asset(
                        type=AssetType.photo,
                        original_path=str(root / "photo.jpg"),
                        original_bytes=123,
                        original_mime="image/jpeg",
                    )
                    session.add(asset)
                    session.commit()

                job_id = str(uuid4())

                def failing_metadata(session, asset_id):
                    raise MetadataNotFoundError("missing")

                worker = MediaWorker(
                    queue,
                    session_factory,
                    config,
                    metadata_handler=failing_metadata,
                    now_fn=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
                )

                queue.enqueue(
                    Job(
                        name=JobType.metadata.value,
                        payload={"asset_id": asset.id},
                        id=job_id,
                    )
                )

                processed = worker.run_once()
                self.assertTrue(processed)

                with session_factory() as session:
                    db_job = session.get(JobRecord, job_id)
                    self.assertIsNotNone(db_job)
                    self.assertEqual(db_job.status, JobStatus.failed)
                    self.assertEqual(db_job.payload.get("asset_id"), asset.id)
                    self.assertIsNotNone(db_job.payload.get("failed_at"))
                    # MediaWorker sets finished_at to failed_at when missing.
                    self.assertEqual(db_job.payload.get("finished_at"), db_job.payload.get("failed_at"))

                # No retry means the queue should be empty now.
                self.assertIsNone(queue.dequeue())
        finally:
            engine.dispose()

    def test_duplicate_transcode_jobs_fail_fast(self) -> None:
        session_factory, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config = _test_config(root)
                queue = Queue(InMemoryQueueBackend())
                now = datetime(2026, 1, 1, tzinfo=timezone.utc)

                with session_factory() as session:
                    asset = Asset(
                        type=AssetType.video,
                        original_path=str(root / "video.mp4"),
                        original_bytes=123,
                        original_mime="video/mp4",
                    )
                    session.add(asset)
                    session.commit()

                    existing = JobRecord(
                        id=str(uuid4()),
                        type=JobType.transcode,
                        status=JobStatus.running,
                        payload={"asset_id": asset.id},
                    )
                    session.add(existing)
                    session.commit()

                job_id = str(uuid4())
                handler = MagicMock()

                worker = MediaWorker(
                    queue,
                    session_factory,
                    config,
                    transcode_handler=handler,
                    now_fn=lambda: now,
                )

                queue.enqueue(
                    Job(
                        name=JobType.transcode.value,
                        payload={"asset_id": asset.id},
                        id=job_id,
                    )
                )

                processed = worker.run_once()
                self.assertTrue(processed)
                handler.assert_not_called()

                with session_factory() as session:
                    db_job = session.get(JobRecord, job_id)
                    self.assertIsNotNone(db_job)
                    self.assertEqual(db_job.status, JobStatus.failed)
                    error = (db_job.payload or {}).get("error")
                    self.assertIsInstance(error, dict)
                    self.assertEqual(error.get("type"), "duplicate")
                    self.assertIsNotNone(db_job.payload.get("finished_at"))
        finally:
            engine.dispose()


class MediaWorkerCliTest(unittest.TestCase):
    def test_main_once_disposes_engine(self) -> None:
        fake_engine = MagicMock()
        fake_session_factory = MagicMock()
        fake_queue = MagicMock()
        fake_config = SimpleNamespace(
            app=SimpleNamespace(log_level="INFO"),
            redis=SimpleNamespace(),
            paths=SimpleNamespace(derived=Path("/tmp")),
        )

        with patch.object(media_worker, "load_config", return_value=fake_config), patch.object(
            media_worker, "configure_logging"
        ), patch.object(media_worker, "create_engine_from_config", return_value=fake_engine), patch.object(
            media_worker, "create_session_factory", return_value=fake_session_factory
        ), patch.object(media_worker, "create_redis_client"), patch.object(
            media_worker, "RedisQueueBackend"
        ), patch.object(media_worker, "Queue", return_value=fake_queue), patch.object(
            media_worker, "MediaWorker"
        ) as worker_cls:
            worker = MagicMock()
            worker_cls.return_value = worker
            result = media_worker.main(["--once"])

        self.assertEqual(result, 0)
        worker.run_once.assert_called_once()
        fake_engine.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
