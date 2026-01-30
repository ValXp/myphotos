import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType, AssetVariantKind
from app.db.models import Asset, AssetVariant
from app.db.session import create_engine_from_config, create_session_factory


class AssetMediaEndpointTest(unittest.TestCase):
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

    def test_thumbnail_endpoint_returns_file(self) -> None:
        asset_id = "00000000-0000-0000-0000-000000003111"
        thumb_bytes = b"thumb-data"
        thumb_path = (
            Path(self.config.paths.derived)
            / asset_id
            / "thumb"
            / "thumb_sm.jpg"
        )
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(thumb_bytes)

        original_path = Path(self.config.paths.originals) / "thumb.jpg"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(b"original")

        asset = Asset(
            id=asset_id,
            type=AssetType.photo,
            original_path=str(original_path),
            original_bytes=8,
            original_mime="image/jpeg",
        )
        variant = AssetVariant(
            asset_id=asset_id,
            kind=AssetVariantKind.thumb,
            profile="thumb_sm",
            path=str(thumb_path),
            bytes=len(thumb_bytes),
        )
        with self.session_factory() as db:
            db.add(asset)
            db.add(variant)
            db.commit()

        response = self.client.get(f"/assets/{asset_id}/thumb", params={"profile": "thumb_sm"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, thumb_bytes)
        self.assertTrue(response.headers["content-type"].startswith("image/jpeg"))
        self.assertIn("cache-control", response.headers)

    def test_original_endpoint_supports_range_requests(self) -> None:
        asset_id = "00000000-0000-0000-0000-000000004111"
        original_bytes = b"0123456789"
        original_path = Path(self.config.paths.originals) / "range.jpg"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(original_bytes)

        asset = Asset(
            id=asset_id,
            type=AssetType.photo,
            original_path=str(original_path),
            original_bytes=len(original_bytes),
            original_mime="image/jpeg",
        )
        with self.session_factory() as db:
            db.add(asset)
            db.commit()

        response = self.client.get(
            f"/assets/{asset_id}/original",
            headers={"Range": "bytes=2-5"},
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"2345")
        self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
        self.assertEqual(response.headers["content-length"], "4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertTrue(response.headers["content-type"].startswith("image/jpeg"))
        self.assertIn("cache-control", response.headers)


if __name__ == "__main__":
    unittest.main()
