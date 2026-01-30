from __future__ import annotations

import unittest

from app.db.enums import AssetType
from app.db.models import Asset, AssetVariant
from app.media.thumbnails import run_thumbnail_job
from app.media.variants import THUMBNAIL_PROFILES
from tests.integration_harness import IntegrationTestCase


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
        with open(path, "wb") as handle:
            handle.write(f"{self.width}x{self.height}".encode("ascii"))


class FakeVips:
    Image = FakeImage


class MediaPipelineIntegrationTest(IntegrationTestCase):
    def test_thumbnail_job_persists_variants(self) -> None:
        originals = self.harness.config.paths.originals
        photo = originals / "photo.jpg"
        photo.write_bytes(b"image")

        with self.harness.session_factory() as db:
            asset = Asset(
                type=AssetType.photo,
                original_path=str(photo),
                original_bytes=photo.stat().st_size,
                original_mime="image/jpeg",
            )
            db.add(asset)
            db.flush()

            run_thumbnail_job(
                db,
                asset.id,
                derived_root=self.harness.config.paths.derived,
                vips_module=FakeVips,
            )
            db.commit()

            variants = db.query(AssetVariant).all()

        self.assertEqual(len(variants), len(THUMBNAIL_PROFILES))


if __name__ == "__main__":
    unittest.main()
