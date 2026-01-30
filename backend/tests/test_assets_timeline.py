import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.enums import AssetType
from app.db.models import Asset
from app.db.session import create_engine_from_config, create_session_factory


class TimelinePaginationTest(unittest.TestCase):
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

    def test_cursor_pagination_newest_first(self) -> None:
        base = datetime(2024, 1, 3, tzinfo=timezone.utc)
        assets = [
            Asset(
                id="00000000-0000-0000-0000-000000000003",
                type=AssetType.photo,
                captured_at=base,
                original_path="/tmp/a.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000002",
                type=AssetType.photo,
                captured_at=base - timedelta(days=1),
                original_path="/tmp/b.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
            Asset(
                id="00000000-0000-0000-0000-000000000001",
                type=AssetType.photo,
                captured_at=base - timedelta(days=1),
                original_path="/tmp/c.jpg",
                original_bytes=10,
                original_mime="image/jpeg",
            ),
        ]
        with self.session_factory() as db:
            db.add_all(assets)
            db.commit()

        response = self.client.get("/assets?limit=2")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        items = body["items"]
        self.assertEqual([item["id"] for item in items], [assets[0].id, assets[1].id])
        self.assertIsNotNone(body["next_cursor"])

        next_response = self.client.get(
            f"/assets?limit=2&cursor={body['next_cursor']}"
        )
        self.assertEqual(next_response.status_code, 200)
        next_body = next_response.json()
        next_items = next_body["items"]
        self.assertEqual([item["id"] for item in next_items], [assets[2].id])
        self.assertIsNone(next_body["next_cursor"])


if __name__ == "__main__":
    unittest.main()
