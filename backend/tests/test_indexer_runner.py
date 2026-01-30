import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Asset
from app.ingest.jobs import METADATA_JOB_NAME, THUMB_JOB_NAME
from app.queue import InMemoryQueueBackend, Queue
from workers.indexer import IndexerRunner


def _create_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    return session_factory, engine


def _drain_queue(queue: Queue) -> list[str]:
    names: list[str] = []
    while True:
        job = queue.dequeue()
        if job is None:
            break
        names.append(job.name)
    return names


class IndexerRunnerTest(unittest.TestCase):
    def test_once_creates_assets_and_enqueues_jobs(self) -> None:
        session_factory, engine = _create_session_factory()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                photo.write_bytes(b"image")

                queue = Queue(InMemoryQueueBackend())
                runner = IndexerRunner(
                    queue,
                    session_factory,
                    [root],
                    poll_interval_seconds=0,
                    scan_interval_seconds=0,
                )

                runner.run_once()

                with session_factory() as session:
                    assets = session.query(Asset).all()
                    self.assertEqual(len(assets), 1)
                    self.assertEqual(
                        assets[0].original_path,
                        str(photo.resolve(strict=False)),
                    )

                names = _drain_queue(queue)
                self.assertEqual(names, [METADATA_JOB_NAME, THUMB_JOB_NAME])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
