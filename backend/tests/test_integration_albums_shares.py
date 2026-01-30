from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.db.enums import AssetType
from app.db.models import Asset
from tests.integration_harness import IntegrationTestCase


class AlbumsSharesIntegrationTest(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.session_store = self.harness.make_session_store()
        self.app = self.harness.make_app(session_store=self.session_store)
        self.client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.harness.config.session.cookie_name, session.id)

    def test_share_link_allows_public_album_access(self) -> None:
        originals = self.harness.config.paths.originals
        photo = originals / "album-photo.jpg"
        photo.write_bytes(b"image")

        with self.harness.session_factory() as db:
            asset = Asset(
                type=AssetType.photo,
                original_path=str(photo),
                original_bytes=photo.stat().st_size,
                original_mime="image/jpeg",
            )
            db.add(asset)
            db.commit()
            asset_id = asset.id

        album_response = self.client.post("/albums", json={"title": "Trip"})
        self.assertEqual(album_response.status_code, 200)
        album_id = album_response.json()["id"]

        add_response = self.client.post(
            f"/albums/{album_id}/items",
            json={"asset_ids": [asset_id]},
        )
        self.assertEqual(add_response.status_code, 200)

        share_response = self.client.post(f"/albums/{album_id}/shares")
        self.assertEqual(share_response.status_code, 200)
        token = share_response.json()["token"]

        public_album = self.client.get(f"/public/shares/{token}/album")
        self.assertEqual(public_album.status_code, 200)
        self.assertEqual(public_album.json()["id"], album_id)

        public_assets = self.client.get(f"/public/shares/{token}/assets")
        self.assertEqual(public_assets.status_code, 200)
        items = public_assets.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], asset_id)


if __name__ == "__main__":
    unittest.main()
