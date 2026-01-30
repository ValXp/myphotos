import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.session import create_engine_from_config, create_session_factory


class LibraryAccessControlTest(unittest.TestCase):
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

    def test_assets_endpoints_require_owner_session(self) -> None:
        endpoints = (
            ("GET", "/assets"),
            ("GET", "/assets/asset-id"),
            ("GET", "/assets/asset-id/thumb"),
            ("GET", "/assets/asset-id/original"),
            ("GET", "/assets/asset-id/stream"),
            ("GET", "/assets/asset-id/live"),
        )
        for method, path in endpoints:
            response = self.client.request(method, path)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "owner session required")


if __name__ == "__main__":
    unittest.main()
