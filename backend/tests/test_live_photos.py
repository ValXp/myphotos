import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetType, AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.ingest.live_photos import link_live_photo_pairs
from app.media.live_video import run_live_video_job
from app.media.variants import LIVE_VIDEO_PROFILE, variant_output_path


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


def _fake_live_video_generator(source_path: Path, output_path: Path) -> None:
    del source_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"live-video")


class LivePhotoLinkingTest(unittest.TestCase):
    def test_link_live_photo_pairs_sets_type_and_link(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                still_path = root / "IMG_1001.jpg"
                video_path = root / "IMG_1001.mov"
                still_path.write_bytes(b"still")
                video_path.write_bytes(b"video")

                still = Asset(
                    type=AssetType.photo,
                    original_path=str(still_path),
                    original_bytes=still_path.stat().st_size,
                    original_mime="image/jpeg",
                )
                video = Asset(
                    type=AssetType.video,
                    original_path=str(video_path),
                    original_bytes=video_path.stat().st_size,
                    original_mime="video/quicktime",
                )
                session.add_all([still, video])
                session.flush()

                links = link_live_photo_pairs(session)

                self.assertEqual(len(links), 1)
                self.assertEqual(still.type, AssetType.live_photo)
                self.assertEqual(still.live_photo_video_id, video.id)
        finally:
            session.close()
            engine.dispose()

    def test_link_live_photo_pairs_uses_duration_and_capture_time(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                still_path = root / "IMG_3001.jpg"
                video_path = root / "VID_9001.mov"
                still_path.write_bytes(b"still")
                video_path.write_bytes(b"video")

                captured_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

                still = Asset(
                    type=AssetType.photo,
                    original_path=str(still_path),
                    original_bytes=still_path.stat().st_size,
                    original_mime="image/jpeg",
                    captured_at=captured_at,
                )
                video = Asset(
                    type=AssetType.video,
                    original_path=str(video_path),
                    original_bytes=video_path.stat().st_size,
                    original_mime="video/quicktime",
                    captured_at=captured_at + timedelta(milliseconds=500),
                    duration_ms=2000,
                )
                session.add_all([still, video])
                session.flush()

                links = link_live_photo_pairs(session)

                self.assertEqual(len(links), 1)
                self.assertEqual(still.type, AssetType.live_photo)
                self.assertEqual(still.live_photo_video_id, video.id)
        finally:
            session.close()
            engine.dispose()


class LiveVideoVariantTest(unittest.TestCase):
    def test_run_live_video_job_creates_variant(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                still_path = root / "IMG_2001.jpg"
                video_path = root / "IMG_2001.mov"
                derived_root = root / "derived"
                still_path.write_bytes(b"still")
                video_path.write_bytes(b"video")

                still = Asset(
                    type=AssetType.photo,
                    original_path=str(still_path),
                    original_bytes=still_path.stat().st_size,
                    original_mime="image/jpeg",
                )
                video = Asset(
                    type=AssetType.video,
                    original_path=str(video_path),
                    original_bytes=video_path.stat().st_size,
                    original_mime="video/quicktime",
                )
                session.add_all([still, video])
                session.flush()

                link_live_photo_pairs(session)

                variant = run_live_video_job(
                    session,
                    still.id,
                    derived_root=derived_root,
                    generator=_fake_live_video_generator,
                )

                self.assertEqual(variant.kind, AssetVariantKind.live_video)
                self.assertEqual(variant.profile, LIVE_VIDEO_PROFILE.name)
                expected_path = variant_output_path(derived_root, still.id, LIVE_VIDEO_PROFILE)
                self.assertEqual(variant.path, str(expected_path))
                self.assertTrue(expected_path.exists())
                stored = session.query(AssetVariant).one()
                self.assertEqual(stored.id, variant.id)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
