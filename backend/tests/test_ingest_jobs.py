import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset
from app.ingest.jobs import (
    AssetChange,
    METADATA_JOB_NAME,
    THUMB_JOB_NAME,
    TRANSCODE_JOB_NAME,
    apply_watch_events,
    enqueue_for_change,
    enqueue_scan_jobs,
    jobs_for_asset,
)
from app.ingest.watcher import WatchEvent, WatchEventKind
from app.queue import InMemoryQueueBackend, Job, Queue


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


def _drain_queue(queue: Queue) -> list[str]:
    names: list[str] = []
    while True:
        job = queue.dequeue()
        if job is None:
            break
        names.append(job.name)
    return names


def _drain_jobs(queue: Queue) -> list[Job]:
    jobs: list[Job] = []
    while True:
        job = queue.dequeue()
        if job is None:
            break
        jobs.append(job)
    return jobs


class IngestJobsTest(unittest.TestCase):
    def test_jobs_for_photo_asset(self) -> None:
        asset = Asset(
            id="asset-photo",
            type=AssetType.photo,
            original_path="/tmp/photo.jpg",
            original_bytes=123,
            original_mime="image/jpeg",
        )
        jobs = jobs_for_asset(asset)
        self.assertEqual([job.name for job in jobs], [METADATA_JOB_NAME, THUMB_JOB_NAME])

    def test_jobs_for_video_asset(self) -> None:
        asset = Asset(
            id="asset-video",
            type=AssetType.video,
            original_path="/tmp/video.mp4",
            original_bytes=456,
            original_mime="video/mp4",
        )
        jobs = jobs_for_asset(asset)
        self.assertEqual(
            [job.name for job in jobs],
            [METADATA_JOB_NAME, THUMB_JOB_NAME, TRANSCODE_JOB_NAME],
        )

    def test_enqueue_for_change_skips_unchanged(self) -> None:
        asset = Asset(
            id="asset-unchanged",
            type=AssetType.photo,
            original_path="/tmp/photo.jpg",
            original_bytes=123,
            original_mime="image/jpeg",
        )
        queue = Queue(InMemoryQueueBackend())
        change = AssetChange(asset=asset, created=False, updated=False)

        jobs = enqueue_for_change(queue, change)

        self.assertEqual(jobs, [])
        self.assertEqual(_drain_queue(queue), [])

    def test_scan_enqueues_for_new_and_updated_assets(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                video = root / "clip.mp4"
                photo.write_bytes(b"image")
                video.write_bytes(b"video")

                queue = Queue(InMemoryQueueBackend())
                enqueue_scan_jobs(session, [root], queue)

                names = _drain_queue(queue)
                counts = Counter(names)
                self.assertEqual(counts[METADATA_JOB_NAME], 2)
                self.assertEqual(counts[THUMB_JOB_NAME], 2)
                self.assertEqual(counts[TRANSCODE_JOB_NAME], 1)

                enqueue_scan_jobs(session, [root], queue)
                self.assertEqual(_drain_queue(queue), [])

                photo.write_bytes(b"updated")
                enqueue_scan_jobs(session, [root], queue)
                names = _drain_queue(queue)
                self.assertEqual(Counter(names)[METADATA_JOB_NAME], 1)
                self.assertEqual(Counter(names)[THUMB_JOB_NAME], 1)
                self.assertEqual(Counter(names)[TRANSCODE_JOB_NAME], 0)
        finally:
            session.close()
            engine.dispose()

    def test_watch_add_event_enqueues_jobs(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                photo.write_bytes(b"image")
                resolved = photo.resolve(strict=False)

                queue = Queue(InMemoryQueueBackend())
                event = WatchEvent(kind=WatchEventKind.add, paths=(resolved,))
                stats = apply_watch_events(session, [event], queue)

                names = _drain_queue(queue)
                self.assertEqual(names, [METADATA_JOB_NAME, THUMB_JOB_NAME])
                self.assertEqual(stats.added, 1)
                self.assertEqual(stats.enqueued, 2)
        finally:
            session.close()
            engine.dispose()

    def test_scan_links_live_photo_and_enqueues_transcode(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                still_path = root / "IMG_1234.jpg"
                video_path = root / "IMG_1234.mov"
                still_path.write_bytes(b"still")
                video_path.write_bytes(b"video")

                queue = Queue(InMemoryQueueBackend())
                enqueue_scan_jobs(session, [root], queue)

                assets = session.query(Asset).all()
                still = next(asset for asset in assets if asset.original_path.endswith("IMG_1234.jpg"))
                video = next(asset for asset in assets if asset.original_path.endswith("IMG_1234.mov"))

                self.assertEqual(still.type, AssetType.live_photo)
                self.assertEqual(still.live_photo_video_id, video.id)

                jobs = _drain_jobs(queue)
                transcodes = [job for job in jobs if job.name == TRANSCODE_JOB_NAME]
                transcode_ids = {job.payload.get("asset_id") for job in transcodes}
                self.assertEqual(transcode_ids, {still.id, video.id})
        finally:
            session.close()
            engine.dispose()

    def test_watch_add_links_live_photo_and_enqueues_transcode(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                still_path = root / "IMG_5678.jpg"
                video_path = root / "IMG_5678.mov"
                still_path.write_bytes(b"still")
                video_path.write_bytes(b"video")

                queue = Queue(InMemoryQueueBackend())
                event = WatchEvent(
                    kind=WatchEventKind.add,
                    paths=(
                        still_path.resolve(strict=False),
                        video_path.resolve(strict=False),
                    ),
                )
                stats = apply_watch_events(session, [event], queue)

                assets = session.query(Asset).all()
                still = next(asset for asset in assets if asset.original_path.endswith("IMG_5678.jpg"))
                video = next(asset for asset in assets if asset.original_path.endswith("IMG_5678.mov"))

                self.assertEqual(still.type, AssetType.live_photo)
                self.assertEqual(still.live_photo_video_id, video.id)

                jobs = _drain_jobs(queue)
                transcodes = [job for job in jobs if job.name == TRANSCODE_JOB_NAME]
                transcode_ids = {job.payload.get("asset_id") for job in transcodes}
                self.assertEqual(transcode_ids, {still.id, video.id})
                self.assertEqual(stats.enqueued, len(jobs))
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
