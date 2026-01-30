import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset
from app.db.session import create_engine_from_config, create_session_factory


class PublicOriginalDownloadTest(unittest.TestCase):
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
        self.owner_client = TestClient(self.app)
        self.public_client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.owner_client.cookies.set(self.config.session.cookie_name, session.id)

    def test_public_original_download_scoped_to_album(self) -> None:
        originals_root = Path(self.config.paths.originals)
        originals_root.mkdir(parents=True, exist_ok=True)
        original_a = originals_root / "a.jpg"
        original_b = originals_root / "b.jpg"
        original_a.write_bytes(b"alpha")
        original_b.write_bytes(b"bravo")

        asset_a = Asset(
            id="00000000-0000-0000-0000-000000009111",
            type=AssetType.photo,
            original_path="a.jpg",
            original_bytes=original_a.stat().st_size,
            original_mime="image/jpeg",
        )
        asset_b = Asset(
            id="00000000-0000-0000-0000-000000009112",
            type=AssetType.photo,
            original_path="b.jpg",
            original_bytes=original_b.stat().st_size,
            original_mime="image/jpeg",
        )
        with self.session_factory() as db:
            db.add_all([asset_a, asset_b])
            db.commit()

        album_a_response = self.owner_client.post("/albums", json={"title": "A"})
        self.assertEqual(album_a_response.status_code, 200)
        album_a_id = album_a_response.json()["id"]
        album_b_response = self.owner_client.post("/albums", json={"title": "B"})
        self.assertEqual(album_b_response.status_code, 200)
        album_b_id = album_b_response.json()["id"]

        add_a_response = self.owner_client.post(
            f"/albums/{album_a_id}/items",
            json={"asset_ids": [asset_a.id]},
        )
        self.assertEqual(add_a_response.status_code, 200)
        add_b_response = self.owner_client.post(
            f"/albums/{album_b_id}/items",
            json={"asset_ids": [asset_b.id]},
        )
        self.assertEqual(add_b_response.status_code, 200)

        share_response = self.owner_client.post(f"/albums/{album_a_id}/shares")
        self.assertEqual(share_response.status_code, 200)
        token = share_response.json()["token"]

        public_response = self.public_client.get(
            f"/public/shares/{token}/assets/{asset_a.id}/original"
        )
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.content, b"alpha")
        self.assertTrue(public_response.headers["content-type"].startswith("image/jpeg"))
        self.assertIn("cache-control", public_response.headers)

        blocked_response = self.public_client.get(
            f"/public/shares/{token}/assets/{asset_b.id}/original"
        )
        self.assertEqual(blocked_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
