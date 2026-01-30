import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset, AssetVariant
from app.media.transcode import (
    TranscodeError,
    TranscodeNotFoundError,
    build_master_manifest,
    format_segment_path,
    master_manifest_path,
    run_transcode_job,
    transcode_playlist_path,
    transcode_profiles_for_asset,
    transcode_segment_pattern,
)
from app.media.variants import VIDEO_RENDITION_PROFILES


def _create_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )()
    return session, engine


def _fake_transcoder(
    source_path: Path,
    playlist_path: Path,
    segment_pattern: Path,
    profile,
) -> None:
    del source_path, profile
    playlist_path.parent.mkdir(parents=True, exist_ok=True)
    segment_path = format_segment_path(segment_pattern, 0)
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_path.write_bytes(b"segment")
    playlist_path.write_text("#EXTM3U\n", encoding="ascii")


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffmpeg_supports_libx264() -> bool:
    if not _ffmpeg_available():
        return False
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    output = f"{result.stdout}\n{result.stderr}"
    return "libx264" in output


def _generate_fixture_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:duration=1:rate=30",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class TranscodeProfileTest(unittest.TestCase):
    def test_profiles_for_video_and_live_photo(self) -> None:
        self.assertEqual(
            transcode_profiles_for_asset(AssetType.video), VIDEO_RENDITION_PROFILES
        )
        self.assertEqual(
            transcode_profiles_for_asset(AssetType.live_photo), VIDEO_RENDITION_PROFILES
        )

    def test_profiles_for_photo_raises(self) -> None:
        with self.assertRaises(TranscodeError):
            transcode_profiles_for_asset(AssetType.photo)

    def test_transcode_paths(self) -> None:
        derived_root = Path("/data/derived")
        asset_id = "asset-123"
        profile = VIDEO_RENDITION_PROFILES[0]
        playlist = transcode_playlist_path(derived_root, asset_id, profile)
        self.assertEqual(
            playlist,
            derived_root
            / asset_id
            / "video_transcode"
            / profile.filename(),
        )
        segment_pattern = transcode_segment_pattern(derived_root, asset_id, profile)
        self.assertEqual(segment_pattern.name, f"{profile.name}_%03d.ts")
        segment_zero = format_segment_path(segment_pattern, 0)
        self.assertTrue(segment_zero.name.endswith("_000.ts"))

    def test_master_manifest_contains_profiles(self) -> None:
        manifest = build_master_manifest(VIDEO_RENDITION_PROFILES)
        for profile in VIDEO_RENDITION_PROFILES:
            self.assertIn(profile.filename(), manifest)


class TranscodeJobTest(unittest.TestCase):
    def test_run_transcode_job_creates_variants(self) -> None:
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

                run_transcode_job(
                    session,
                    asset.id,
                    derived_root=derived,
                    transcode_func=_fake_transcoder,
                )

                variants = session.query(AssetVariant).all()
                self.assertEqual(len(variants), len(VIDEO_RENDITION_PROFILES))
                master = master_manifest_path(derived, asset.id)
                self.assertTrue(master.exists())

                for profile in VIDEO_RENDITION_PROFILES:
                    playlist = transcode_playlist_path(derived, asset.id, profile)
                    self.assertTrue(playlist.exists())
                    segment_pattern = transcode_segment_pattern(derived, asset.id, profile)
                    segment_path = format_segment_path(segment_pattern, 0)
                    self.assertTrue(segment_path.exists())
        finally:
            session.close()
            engine.dispose()

    def test_run_transcode_job_missing_asset_raises(self) -> None:
        session, engine = _create_session()
        try:
            with self.assertRaises(TranscodeNotFoundError):
                run_transcode_job(
                    session,
                    "missing",
                    derived_root=Path("/tmp/derived"),
                    transcode_func=_fake_transcoder,
                )
        finally:
            session.close()
            engine.dispose()


class TranscodeIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(_ffmpeg_available(), "ffmpeg not installed")
    @unittest.skipUnless(_ffmpeg_supports_libx264(), "libx264 encoder not available")
    def test_transcode_outputs_manifest_and_segments(self) -> None:
        session, engine = _create_session()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                video = root / "fixture.mp4"
                _generate_fixture_video(video)
                derived = root / "derived"

                asset = Asset(
                    type=AssetType.video,
                    original_path=str(video),
                    original_bytes=video.stat().st_size,
                    original_mime="video/mp4",
                )
                session.add(asset)
                session.flush()

                run_transcode_job(
                    session,
                    asset.id,
                    derived_root=derived,
                    ffmpeg_path="ffmpeg",
                )

                master = master_manifest_path(derived, asset.id)
                self.assertTrue(master.exists())

                for profile in VIDEO_RENDITION_PROFILES:
                    playlist = transcode_playlist_path(derived, asset.id, profile)
                    self.assertTrue(playlist.exists())
                    segments = list(playlist.parent.glob(f"{profile.name}_*.ts"))
                    self.assertTrue(segments)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
