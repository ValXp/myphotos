import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset
from app.db.session import create_engine_from_config, create_session_factory


class ShareLinkIntegrationTest(unittest.TestCase):
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

    def test_share_link_create_revoke_and_public_access(self) -> None:
        album_response = self.owner_client.post("/albums", json={"title": "Travel"})
        self.assertEqual(album_response.status_code, 200)
        album = album_response.json()

        share_response = self.owner_client.post(f"/albums/{album['id']}/shares")
        self.assertEqual(share_response.status_code, 200)
        share = share_response.json()
        self.assertEqual(share["album_id"], album["id"])
        self.assertTrue(share["token"])
        self.assertIsNone(share["revoked_at"])

        public_response = self.public_client.get(
            f"/public/shares/{share['token']}/album"
        )
        self.assertEqual(public_response.status_code, 200)
        public_album = public_response.json()
        self.assertEqual(public_album["id"], album["id"])
        self.assertEqual(public_album["title"], album["title"])

        revoke_response = self.owner_client.delete(
            f"/albums/{album['id']}/shares/{share['id']}"
        )
        self.assertEqual(revoke_response.status_code, 200)
        revoked = revoke_response.json()
        self.assertIsNotNone(revoked["revoked_at"])

        blocked_response = self.public_client.get(
            f"/public/shares/{share['token']}/album"
        )
        self.assertEqual(blocked_response.status_code, 404)

    def test_share_token_scopes_to_album(self) -> None:
        album_a_response = self.owner_client.post("/albums", json={"title": "A"})
        self.assertEqual(album_a_response.status_code, 200)
        album_a = album_a_response.json()
        album_b_response = self.owner_client.post("/albums", json={"title": "B"})
        self.assertEqual(album_b_response.status_code, 200)
        album_b = album_b_response.json()

        share_response = self.owner_client.post(f"/albums/{album_a['id']}/shares")
        self.assertEqual(share_response.status_code, 200)
        token = share_response.json()["token"]

        public_response = self.public_client.get(f"/public/shares/{token}/album")
        self.assertEqual(public_response.status_code, 200)
        public_album = public_response.json()
        self.assertEqual(public_album["id"], album_a["id"])
        self.assertNotEqual(public_album["id"], album_b["id"])

    def test_public_album_asset_listing_scoped(self) -> None:
        assets = [
            Asset(
                id="00000000-0000-0000-0000-000000000601",
                type=AssetType.photo,
                original_path="/tmp/a.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000602",
                type=AssetType.photo,
                original_path="/tmp/b.jpg",
                original_bytes=11,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000603",
                type=AssetType.photo,
                original_path="/tmp/c.jpg",
                original_bytes=12,
                original_mime="image/jpeg",
            ),
        ]
        with self.session_factory() as db:
            db.add_all(assets)
            db.commit()

        album_a_response = self.owner_client.post("/albums", json={"title": "A"})
        self.assertEqual(album_a_response.status_code, 200)
        album_a_id = album_a_response.json()["id"]
        album_b_response = self.owner_client.post("/albums", json={"title": "B"})
        self.assertEqual(album_b_response.status_code, 200)
        album_b_id = album_b_response.json()["id"]

        add_response = self.owner_client.post(
            f"/albums/{album_a_id}/items",
            json={"asset_ids": [assets[1].id, assets[0].id]},
        )
        self.assertEqual(add_response.status_code, 200)
        add_response = self.owner_client.post(
            f"/albums/{album_b_id}/items",
            json={"asset_ids": [assets[2].id]},
        )
        self.assertEqual(add_response.status_code, 200)

        share_response = self.owner_client.post(f"/albums/{album_a_id}/shares")
        self.assertEqual(share_response.status_code, 200)
        token = share_response.json()["token"]

        public_response = self.public_client.get(f"/public/shares/{token}/assets")
        self.assertEqual(public_response.status_code, 200)
        items = public_response.json()["items"]
        self.assertEqual([item["id"] for item in items], [assets[1].id, assets[0].id])
        self.assertNotIn(assets[2].id, {item["id"] for item in items})
        for item in items:
            self.assertNotIn("original_path", item)
            self.assertNotIn("original_mime", item)


if __name__ == "__main__":
    unittest.main()
