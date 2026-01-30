import base64
import shutil
import subprocess
import unittest
from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset
from app.media.metadata import run_metadata_job

JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "/2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAVAQEBAAAAAAAAAAAAAAAAAAAAAv"
    "/aAAwDAQACEAMQAAABywAAAAAAAAAB/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPwB//8QAFBEB"
    "AAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwB//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwB//9k="
)

EXIFTOOL = shutil.which("exiftool")
FFPROBE = shutil.which("ffprobe")
FFMPEG = shutil.which("ffmpeg")


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


class MetadataIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(EXIFTOOL, "exiftool not installed")
    def test_exiftool_metadata_job_updates_asset(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                photo.write_bytes(base64.b64decode(JPEG_BASE64))

                subprocess.run(
                    [
                        EXIFTOOL,
                        "-overwrite_original",
                        "-DateTimeOriginal=2020:01:02 03:04:05",
                        "-OffsetTimeOriginal=+00:00",
                        "-GPSLatitude=37.7749",
                        "-GPSLongitude=-122.4194",
                        str(photo),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                asset = Asset(
                    type=AssetType.photo,
                    original_path=str(photo),
                    original_bytes=photo.stat().st_size,
                    original_mime="image/jpeg",
                )
                session.add(asset)
                session.flush()

                run_metadata_job(session, asset.id, exiftool_path=EXIFTOOL)

                self.assertEqual(asset.width, 16)
                self.assertEqual(asset.height, 16)
                self.assertIsNotNone(asset.captured_at)
                self.assertEqual(asset.captured_at.year, 2020)
                self.assertEqual(asset.captured_at.tzinfo, timezone.utc)
                self.assertAlmostEqual(asset.lat or 0.0, 37.7749, places=4)
                self.assertAlmostEqual(asset.lon or 0.0, -122.4194, places=4)
        finally:
            session.close()
            engine.dispose()

    @unittest.skipUnless(FFPROBE, "ffprobe not installed")
    def test_ffprobe_metadata_job_updates_video(self) -> None:
        if FFMPEG is None:
            self.skipTest("ffmpeg not installed")
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                video = root / "clip.mp4"
                subprocess.run(
                    [
                        FFMPEG,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=black:s=320x240:d=1",
                        "-pix_fmt",
                        "yuv420p",
                        "-metadata",
                        "creation_time=2020-01-02T03:04:05Z",
                        str(video),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                asset = Asset(
                    type=AssetType.video,
                    original_path=str(video),
                    original_bytes=video.stat().st_size,
                    original_mime="video/mp4",
                )
                session.add(asset)
                session.flush()

                run_metadata_job(session, asset.id, ffprobe_path=FFPROBE)

                self.assertEqual(asset.width, 320)
                self.assertEqual(asset.height, 240)
                self.assertIsNotNone(asset.duration_ms)
                self.assertGreaterEqual(asset.duration_ms or 0, 800)
                self.assertLessEqual(asset.duration_ms or 0, 1500)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
