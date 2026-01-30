import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import AlbumItem, Asset
from app.db.session import create_engine_from_config, create_session_factory


class AlbumApiIntegrationTest(unittest.TestCase):
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

    def test_album_crud(self) -> None:
        response = self.client.post("/albums", json={"title": "Summer"})
        self.assertEqual(response.status_code, 200)
        created = response.json()
        album_id = created["id"]
        self.assertEqual(created["title"], "Summer")
        self.assertIn("created_at", created)
        self.assertIn("updated_at", created)
        self.assertEqual(created["item_count"], 0)

        list_response = self.client.get("/albums")
        self.assertEqual(list_response.status_code, 200)
        items = list_response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], album_id)

        patch_response = self.client.patch(
            f"/albums/{album_id}", json={"title": "Summer 2024"}
        )
        self.assertEqual(patch_response.status_code, 200)
        patched = patch_response.json()
        self.assertEqual(patched["title"], "Summer 2024")

        delete_response = self.client.delete(f"/albums/{album_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["status"], "deleted")

        list_response = self.client.get("/albums")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["items"], [])

    def test_album_item_add_remove(self) -> None:
        assets = [
            Asset(
                id="00000000-0000-0000-0000-000000000501",
                type=AssetType.photo,
                original_path="/tmp/a.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000502",
                type=AssetType.photo,
                original_path="/tmp/b.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000503",
                type=AssetType.photo,
                original_path="/tmp/c.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
        ]
        with self.session_factory() as db:
            db.add_all(assets)
            db.commit()

        response = self.client.post("/albums", json={"title": "Favorites"})
        self.assertEqual(response.status_code, 200)
        album_id = response.json()["id"]

        add_response = self.client.post(
            f"/albums/{album_id}/items",
            json={"asset_ids": [asset.id for asset in assets]},
        )
        self.assertEqual(add_response.status_code, 200)
        add_body = add_response.json()
        self.assertEqual(len(add_body["added"]), 3)
        self.assertEqual(add_body["item_count"], 3)

        remove_response = self.client.request(
            "DELETE",
            f"/albums/{album_id}/items",
            json={"asset_ids": [assets[0].id, assets[2].id]},
        )
        self.assertEqual(remove_response.status_code, 200)
        remove_body = remove_response.json()
        self.assertEqual(sorted(remove_body["removed"]), [assets[0].id, assets[2].id])
        self.assertEqual(remove_body["item_count"], 1)

        with self.session_factory() as db:
            remaining = (
                db.query(AlbumItem)
                .filter(AlbumItem.album_id == album_id)
                .all()
            )
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].asset_id, assets[1].id)


if __name__ == "__main__":
    unittest.main()
