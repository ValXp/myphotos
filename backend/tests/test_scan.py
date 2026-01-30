import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset
from app.ingest.scan import FullScanJob, asset_type_for_path, guess_mime


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


class FullScanJobTest(unittest.TestCase):
    def test_full_scan_creates_assets(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                video = root / "clip.mp4"
                note = root / "notes.txt"
                photo.write_bytes(b"image")
                video.write_bytes(b"video")
                note.write_text("ignore")

                job = FullScanJob([root])
                stats = job.run(session)

                self.assertEqual(stats.created, 2)
                self.assertEqual(stats.supported, 2)
                assets = session.query(Asset).all()
                self.assertEqual(len(assets), 2)
                by_path = {asset.original_path: asset for asset in assets}
                self.assertIn(str(photo.resolve(strict=False)), by_path)
                self.assertIn(str(video.resolve(strict=False)), by_path)
                self.assertEqual(by_path[str(photo.resolve(strict=False))].type, AssetType.photo)
                self.assertEqual(by_path[str(video.resolve(strict=False))].type, AssetType.video)
                self.assertTrue(by_path[str(photo.resolve(strict=False))].original_mime.startswith("image/"))
                self.assertTrue(by_path[str(video.resolve(strict=False))].original_mime.startswith("video/"))
        finally:
            session.close()
            engine.dispose()

    def test_full_scan_updates_existing_asset(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                photo.write_bytes(b"a")

                job = FullScanJob([photo])
                stats = job.run(session)
                self.assertEqual(stats.created, 1)

                asset = session.query(Asset).one()
                asset_id = asset.id
                self.assertEqual(asset.original_bytes, 1)

                photo.write_bytes(b"abcd")
                stats = job.run(session)

                updated = session.query(Asset).one()
                self.assertEqual(stats.updated, 1)
                self.assertEqual(updated.id, asset_id)
                self.assertEqual(updated.original_bytes, 4)
        finally:
            session.close()
            engine.dispose()

    def test_asset_type_for_path_rejects_unsupported(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notes.txt"
            path.write_text("unsupported")
            with self.assertRaises(ValueError):
                asset_type_for_path(path)

    def test_guess_mime_fallbacks(self) -> None:
        with TemporaryDirectory() as tmpdir:
            image = Path(tmpdir) / "photo.heic"
            image.write_bytes(b"heic")
            video = Path(tmpdir) / "movie.mkv"
            video.write_bytes(b"mkv")
            mime_image = guess_mime(image)
            mime_video = guess_mime(video)
            self.assertTrue(mime_image.startswith("image/"))
            self.assertTrue(mime_video.startswith("video/"))

    def test_scan_reports_missing_root(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                missing = Path(tmpdir) / "missing-root"
                job = FullScanJob([missing])
                stats = job.run(session)
                self.assertEqual(stats.scanned, 0)
                self.assertTrue(stats.errors)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
