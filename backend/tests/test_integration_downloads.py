from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.db.enums import AssetType
from app.db.models import Asset
from tests.integration_harness import IntegrationTestCase


class DownloadsIntegrationTest(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.session_store = self.harness.make_session_store()
        self.app = self.harness.make_app(session_store=self.session_store)
        self.client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.harness.config.session.cookie_name, session.id)

    def test_public_zip_download_flow(self) -> None:
        originals = self.harness.config.paths.originals
        photo = originals / "download-photo.jpg"
        photo.write_bytes(b"zip-me")

        with self.harness.session_factory() as db:
            asset = Asset(
                type=AssetType.photo,
                original_path="download-photo.jpg",
                original_bytes=photo.stat().st_size,
                original_mime="image/jpeg",
            )
            db.add(asset)
            db.commit()
            asset_id = asset.id

        album_response = self.client.post("/albums", json={"title": "Downloads"})
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

        zip_response = self.client.post(f"/public/shares/{token}/zip")
        self.assertEqual(zip_response.status_code, 200)
        zip_payload = zip_response.json()
        self.assertEqual(zip_payload["status"], "done")
        download_url = zip_payload["download_url"]
        self.assertIsNotNone(download_url)

        download_response = self.client.get(download_url)
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.headers.get("content-type"), "application/zip")


if __name__ == "__main__":
    unittest.main()
