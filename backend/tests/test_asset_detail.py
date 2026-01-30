import os
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType, AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.db.session import create_engine_from_config, create_session_factory


class AssetDetailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = load_config(
            {
                "DATA_ROOT": self.temp_dir.name,
                "APP_ENV": "test",
                "DB_URL": f"sqlite+pysqlite:///{os.path.join(self.temp_dir.name, 'test.db')}",
            }
        )
        self.engine = create_engine_from_config(self.config)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.session_store = InMemorySessionStore(default_ttl_seconds=300)
        self.app = create_app(
            self.config,
            session_store=self.session_store,
            db_session_factory=self.session_factory,
        )
        self.client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.config.session.cookie_name, session.id)

    def test_asset_detail_returns_metadata_and_variants(self) -> None:
        asset_id = "00000000-0000-0000-0000-000000001111"
        created_at = datetime(2024, 1, 10, 9, 30, 0, tzinfo=timezone.utc)
        captured_at = datetime(2024, 1, 9, 8, 15, 0, tzinfo=timezone.utc)
        asset = Asset(
            id=asset_id,
            type=AssetType.photo,
            created_at=created_at,
            captured_at=captured_at,
            duration_ms=None,
            width=1920,
            height=1080,
            lat=37.7,
            lon=-122.4,
            hash="hash-1",
            original_path="/tmp/detail.jpg",
            original_bytes=2048,
            original_mime="image/jpeg",
        )
        variant_thumb = AssetVariant(
            id="00000000-0000-0000-0000-000000002222",
            asset_id=asset_id,
            kind=AssetVariantKind.thumb,
            profile="thumb_sm",
            path="/derived/thumb_sm.jpg",
            bytes=128,
            created_at=created_at,
        )
        variant_transcode = AssetVariant(
            id="00000000-0000-0000-0000-000000002223",
            asset_id=asset_id,
            kind=AssetVariantKind.video_transcode,
            profile="hls_360p",
            path="/derived/hls_360p.m3u8",
            bytes=4096,
            created_at=created_at,
        )
        with self.session_factory() as db:
            db.add(asset)
            db.add_all([variant_thumb, variant_transcode])
            db.commit()

        response = self.client.get(f"/assets/{asset_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], asset_id)
        self.assertEqual(body["type"], "photo")
        self.assertEqual(body["created_at"], _expect_iso(created_at))
        self.assertEqual(body["captured_at"], _expect_iso(captured_at))
        self.assertEqual(body["width"], 1920)
        self.assertEqual(body["height"], 1080)
        self.assertEqual(body["lat"], 37.7)
        self.assertEqual(body["lon"], -122.4)
        self.assertEqual(body["hash"], "hash-1")
        self.assertEqual(body["original_path"], "/tmp/detail.jpg")
        self.assertEqual(body["original_bytes"], 2048)
        self.assertEqual(body["original_mime"], "image/jpeg")
        self.assertIsNone(body["live_photo_video_id"])

        variants = body["variants"]
        self.assertEqual(len(variants), 2)
        self.assertEqual(
            [variant["profile"] for variant in variants],
            ["thumb_sm", "hls_360p"],
        )
        self.assertEqual(variants[0]["kind"], "thumb")
        self.assertEqual(variants[1]["kind"], "video_transcode")
        self.assertEqual(variants[0]["path"], "/derived/thumb_sm.jpg")
        self.assertEqual(variants[1]["path"], "/derived/hls_360p.m3u8")

    def test_asset_detail_missing_returns_404(self) -> None:
        response = self.client.get("/assets/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "asset not found")


def _expect_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


if __name__ == "__main__":
    unittest.main()
