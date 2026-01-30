import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
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
from app.db.enums import AssetType, JobStatus, JobType
from app.db.models import Asset, Job as JobRecord
from app.media.metadata import MetadataResult, MetadataToolError
from app.queue import InMemoryQueueBackend, Job, Queue
from workers.media_worker import MediaWorker


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
        ),
        session=SessionConfig(
            ttl_seconds=3600,
            cookie_name="myphotos_session",
        ),
    )


class MediaWorkerTest(unittest.TestCase):
    def test_successful_job_updates_status(self) -> None:
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

                def fake_metadata(session, asset_id):
                    job = session.get(JobRecord, job_id)
                    self.assertIsNotNone(job)
                    self.assertEqual(job.status, JobStatus.running)
                    asset = session.get(Asset, asset_id)
                    self.assertIsNotNone(asset)
                    asset.width = 2048
                    asset.height = 1536
                    return MetadataResult(width=2048, height=1536)

                worker = MediaWorker(
                    queue,
                    session_factory,
                    config,
                    metadata_handler=fake_metadata,
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
                    self.assertEqual(db_job.status, JobStatus.done)
                    self.assertEqual(db_job.payload.get("asset_id"), asset.id)
                    self.assertIn("started_at", db_job.payload)
                    self.assertIn("finished_at", db_job.payload)
                    metadata = db_job.payload.get("metadata")
                    self.assertEqual(metadata.get("width"), 2048)
                    self.assertEqual(metadata.get("height"), 1536)
        finally:
            engine.dispose()

    def test_retryable_failure_reenqueues(self) -> None:
        session_factory, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config = _test_config(root)
                queue = Queue(InMemoryQueueBackend())
                now = datetime(2025, 1, 1, tzinfo=timezone.utc)
                slept: list[float] = []

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
                    job = session.get(JobRecord, job_id)
                    self.assertIsNotNone(job)
                    self.assertEqual(job.status, JobStatus.running)
                    raise MetadataToolError("exiftool missing")

                def fake_sleep(seconds: float) -> None:
                    slept.append(seconds)

                worker = MediaWorker(
                    queue,
                    session_factory,
                    config,
                    metadata_handler=failing_metadata,
                    sleep_fn=fake_sleep,
                    now_fn=lambda: now,
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
                    self.assertEqual(db_job.status, JobStatus.queued)
                    self.assertEqual(db_job.payload.get("attempts"), 1)
                    self.assertEqual(db_job.payload.get("asset_id"), asset.id)
                    self.assertIsNotNone(db_job.payload.get("failed_at"))
                    self.assertIn("error", db_job.payload)

                self.assertTrue(slept)
                queued = queue.dequeue()
                self.assertIsNotNone(queued)
                self.assertEqual(queued.id, job_id)
                self.assertEqual(queued.payload.get("attempts"), 1)
        finally:
            engine.dispose()
