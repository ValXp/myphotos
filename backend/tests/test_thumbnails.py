import base64
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset, AssetVariant
from app.media.thumbnails import (
    ThumbnailNotFoundError,
    compute_thumbnail_size,
    run_thumbnail_job,
)
from app.media.variants import THUMBNAIL_PROFILES, VIDEO_POSTER_PROFILE, variant_output_path


class FakeImage:
    default_width = 400
    default_height = 300

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    @classmethod
    def new_from_file(cls, path: str, access: str = "sequential") -> "FakeImage":
        del path, access
        return cls(cls.default_width, cls.default_height)

    def resize(self, scale: float, kernel: str = "lanczos3") -> "FakeImage":
        del kernel
        width = max(1, int(round(self.width * scale)))
        height = max(1, int(round(self.height * scale)))
        return FakeImage(width, height)

    def write_to_file(self, path: str, **_: object) -> None:
        payload = f"{self.width}x{self.height}".encode("ascii")
        Path(path).write_bytes(payload)


class FakeVips:
    Image = FakeImage


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


def _fake_poster_extractor(video_path: Path, poster_path: Path) -> None:
    del video_path
    poster_path.write_bytes(b"poster")


JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "/2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAVAQEBAAAAAAAAAAAAAAAAAAAAAv"
    "/aAAwDAQACEAMQAAABywAAAAAAAAAB/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPwB//8QAFBEB"
    "AAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwB//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwB//9k="
)


class ThumbnailSizingTest(unittest.TestCase):
    def test_compute_thumbnail_size_no_upscale(self) -> None:
        width, height = compute_thumbnail_size(400, 300, 512, 512)
        self.assertEqual((width, height), (400, 300))

    def test_compute_thumbnail_size_preserves_aspect(self) -> None:
        width, height = compute_thumbnail_size(400, 300, 256, 256)
        self.assertEqual((width, height), (256, 192))

    def test_compute_thumbnail_size_height_only(self) -> None:
        width, height = compute_thumbnail_size(400, 300, None, 150)
        self.assertEqual((width, height), (200, 150))


class ThumbnailJobTest(unittest.TestCase):
    def test_run_thumbnail_job_creates_variants(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                photo.write_bytes(base64.b64decode(JPEG_BASE64))
                derived = root / "derived"

                asset = Asset(
                    type=AssetType.photo,
                    original_path=str(photo),
                    original_bytes=photo.stat().st_size,
                    original_mime="image/jpeg",
                )
                session.add(asset)
                session.flush()

                run_thumbnail_job(
                    session,
                    asset.id,
                    derived_root=derived,
                    vips_module=FakeVips,
                )

                variants = session.query(AssetVariant).all()
                self.assertEqual(len(variants), len(THUMBNAIL_PROFILES))

                for profile in THUMBNAIL_PROFILES:
                    output = variant_output_path(derived, asset.id, profile)
                    self.assertTrue(output.exists())
                    expected = compute_thumbnail_size(
                        FakeImage.default_width,
                        FakeImage.default_height,
                        profile.width,
                        profile.height,
                    )
                    payload = output.read_bytes().decode("ascii")
                    self.assertEqual(payload, f"{expected[0]}x{expected[1]}")
        finally:
            session.close()
            engine.dispose()

    def test_run_thumbnail_job_video_includes_poster(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                video = root / "clip.mp4"
                video.write_bytes(b"video")
                derived = root / "derived"

                asset = Asset(
                    type=AssetType.video,
                    original_path=str(video),
                    original_bytes=video.stat().st_size,
                    original_mime="video/mp4",
                )
                session.add(asset)
                session.flush()

                run_thumbnail_job(
                    session,
                    asset.id,
                    derived_root=derived,
                    vips_module=FakeVips,
                    poster_extractor=_fake_poster_extractor,
                )

                variants = session.query(AssetVariant).all()
                self.assertEqual(len(variants), len(THUMBNAIL_PROFILES) + 1)
                poster_path = variant_output_path(derived, asset.id, VIDEO_POSTER_PROFILE)
                self.assertTrue(poster_path.exists())
        finally:
            session.close()
            engine.dispose()

    def test_run_thumbnail_job_missing_asset_raises(self) -> None:
        session, engine = _create_session()
        try:
            with self.assertRaises(ThumbnailNotFoundError):
                run_thumbnail_job(
                    session,
                    "missing",
                    derived_root=Path("/tmp/derived"),
                    vips_module=FakeVips,
                )
        finally:
            session.close()
            engine.dispose()


try:
    import pyvips  # type: ignore

    PYVIPS_AVAILABLE = True
except Exception:
    PYVIPS_AVAILABLE = False


class ThumbnailIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(PYVIPS_AVAILABLE, "pyvips not installed")
    def test_thumbnail_outputs_are_readable(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                photo = root / "photo.jpg"
                photo.write_bytes(base64.b64decode(JPEG_BASE64))
                derived = root / "derived"

                asset = Asset(
                    type=AssetType.photo,
                    original_path=str(photo),
                    original_bytes=photo.stat().st_size,
                    original_mime="image/jpeg",
                )
                session.add(asset)
                session.flush()

                run_thumbnail_job(
                    session,
                    asset.id,
                    derived_root=derived,
                )

                for profile in THUMBNAIL_PROFILES:
                    output = variant_output_path(derived, asset.id, profile)
                    self.assertTrue(output.exists())
                    image = pyvips.Image.new_from_file(str(output))
                    self.assertGreater(image.width, 0)
                    self.assertGreater(image.height, 0)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
