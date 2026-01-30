import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.ingest.jobs import apply_watch_events
from app.ingest.scan import FullScanJob, normalize_path
from app.ingest.watcher import FilesystemWatcher, WatchEventKind
from app.queue import InMemoryQueueBackend, Queue


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


class IngestFlowIntegrationTest(unittest.TestCase):
    def test_add_move_delete_flow(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                queue = Queue(InMemoryQueueBackend())
                watcher = FilesystemWatcher([root])

                photo = root / "photo.jpg"
                photo.write_bytes(b"image")
                events = watcher.poll()

                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].kind, WatchEventKind.add)
                apply_watch_events(session, events, queue)
                session.commit()

                asset = session.query(Asset).one()
                asset_id = asset.id

                session.add(
                    AssetVariant(
                        asset_id=asset.id,
                        kind=AssetVariantKind.thumb,
                        profile="small",
                        path=str(root / "thumb.jpg"),
                        bytes=123,
                    )
                )
                session.commit()

                moved = root / "renamed.jpg"
                photo.rename(moved)
                events = watcher.poll()

                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].kind, WatchEventKind.move)
                apply_watch_events(session, events, queue)
                session.commit()

                updated = session.query(Asset).one()
                self.assertEqual(updated.id, asset_id)
                self.assertEqual(updated.original_path, normalize_path(moved))

                moved.unlink()
                events = watcher.poll()

                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].kind, WatchEventKind.delete)
                apply_watch_events(session, events, queue)
                session.commit()

                self.assertEqual(session.query(Asset).count(), 0)
                self.assertEqual(session.query(AssetVariant).count(), 0)
        finally:
            session.close()
            engine.dispose()

    def test_full_scan_recovers_missed_add(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                watcher = FilesystemWatcher([root])
                watcher.prime()

                photo = root / "late.jpg"
                photo.write_bytes(b"image")

                stats = FullScanJob([root]).run(session)

                self.assertEqual(stats.created, 1)
                asset = session.query(Asset).one()
                self.assertEqual(asset.original_path, normalize_path(photo))
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
