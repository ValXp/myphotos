from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from fastapi.testclient import TestClient

from app.db.enums import AssetType
from app.db.models import Asset
from tests.integration_harness import IntegrationTestCase


class TimelineIntegrationTest(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.session_store = self.harness.make_session_store()
        self.app = self.harness.make_app(session_store=self.session_store)
        self.client = TestClient(self.app)
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.harness.config.session.cookie_name, session.id)

    def test_timeline_cursor_pagination(self) -> None:
        base = datetime(2024, 1, 3, tzinfo=timezone.utc)
        assets = [
            Asset(
                type=AssetType.photo,
                captured_at=base,
                original_path="/tmp/a.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                type=AssetType.photo,
                captured_at=base - timedelta(days=1),
                original_path="/tmp/b.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                type=AssetType.photo,
                captured_at=base - timedelta(days=2),
                original_path="/tmp/c.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
        ]
        with self.harness.session_factory() as db:
            db.add_all(assets)
            db.commit()

        response = self.client.get("/assets?limit=2")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        items = body["items"]
        self.assertEqual(len(items), 2)
        self.assertIsNotNone(body["next_cursor"])

        next_response = self.client.get(
            f"/assets?limit=2&cursor={body['next_cursor']}"
        )
        self.assertEqual(next_response.status_code, 200)
        next_body = next_response.json()
        self.assertEqual(len(next_body["items"]), 1)
        self.assertIsNone(next_body["next_cursor"])


if __name__ == "__main__":
    unittest.main()
