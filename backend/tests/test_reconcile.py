import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.ingest.reconcile import reconcile_events
from app.ingest.scan import FullScanJob, normalize_path
from app.ingest.watcher import WatchEvent, WatchEventKind


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class ReconcileTest(unittest.TestCase):
    def test_move_updates_asset_path(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                original = root / "photo.jpg"
                original.write_bytes(b"image")

                job = FullScanJob([root])
                job.run(session)

                asset = session.query(Asset).one()
                asset_id = asset.id

                moved = root / "renamed.jpg"
                original.rename(moved)

                event = WatchEvent(
                    kind=WatchEventKind.move,
                    paths=(moved,),
                    previous_paths=(original,),
                )
                stats = reconcile_events(session, [event])
                session.commit()

                updated = session.query(Asset).one()
                self.assertEqual(updated.id, asset_id)
                self.assertEqual(updated.original_path, normalize_path(moved))
                self.assertEqual(stats.moved, 1)
        finally:
            session.close()
            engine.dispose()

    def test_move_matches_by_signature(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                original = root / "photo.jpg"
                original.write_bytes(b"image")

                job = FullScanJob([root])
                job.run(session)

                asset_id = session.query(Asset).one().id

                moved = root / "moved.jpg"
                original.rename(moved)

                event = WatchEvent(
                    kind=WatchEventKind.move,
                    paths=(moved,),
                    previous_paths=(root / "missing.jpg",),
                )
                stats = reconcile_events(session, [event])
                session.commit()

                updated = session.query(Asset).one()
                self.assertEqual(updated.id, asset_id)
                self.assertEqual(updated.original_path, normalize_path(moved))
                self.assertEqual(stats.moved, 1)
        finally:
            session.close()
            engine.dispose()

    def test_move_falls_back_to_hash(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                original = root / "photo.jpg"
                original.write_bytes(b"same-content")

                job = FullScanJob([root])
                job.run(session)

                asset = session.query(Asset).one()
                asset_id = asset.id
                asset.hash = _sha256(original)
                session.commit()

                moved = root / "copy.jpg"
                moved.write_bytes(original.read_bytes())
                original.unlink()

                event = WatchEvent(
                    kind=WatchEventKind.move,
                    paths=(moved,),
                    previous_paths=(root / "missing.jpg",),
                )
                stats = reconcile_events(session, [event])
                session.commit()

                updated = session.query(Asset).one()
                self.assertEqual(updated.id, asset_id)
                self.assertEqual(updated.original_path, normalize_path(moved))
                self.assertEqual(stats.moved, 1)
        finally:
            session.close()
            engine.dispose()

    def test_delete_removes_asset_and_variants(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                original = root / "photo.jpg"
                original.write_bytes(b"image")

                job = FullScanJob([root])
                job.run(session)

                asset = session.query(Asset).one()
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

                event = WatchEvent(
                    kind=WatchEventKind.delete,
                    paths=(original,),
                )
                stats = reconcile_events(session, [event])
                session.commit()

                self.assertEqual(stats.deleted, 1)
                self.assertEqual(session.query(Asset).count(), 0)
                self.assertEqual(session.query(AssetVariant).count(), 0)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
