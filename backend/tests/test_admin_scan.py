import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config
from app.db.base import Base
from app.db.session import create_engine_from_config, create_session_factory
from app.ingest.admin import ScanBackoffPolicy
from app.queue import InMemoryQueueBackend, Queue


class AdminScanTest(unittest.TestCase):
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
        self.queue = Queue(InMemoryQueueBackend())
        self.backoff_policy = ScanBackoffPolicy(large_scan_threshold=1, backoff_seconds=3600)
        self.app = create_app(
            self.config,
            session_store=self.session_store,
            db_session_factory=self.session_factory,
            queue=self.queue,
            scan_backoff=self.backoff_policy,
        )
        self.client = TestClient(self.app)
        self.config.paths.originals.mkdir(parents=True, exist_ok=True)
        self._write_file(self.config.paths.originals / "photo.jpg", b"test")
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.config.session.cookie_name, session.id)

    def test_scan_start_and_status(self) -> None:
        response = self.client.post("/admin/index/scan")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertIsNotNone(body.get("job_id"))
        stats = body.get("stats") or {}
        self.assertGreaterEqual(stats.get("scanned", 0), 1)

        status_response = self.client.get("/admin/index/status")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.json()
        self.assertEqual(status_body["status"], "done")
        self.assertEqual(status_body["job_id"], body["job_id"])

    def test_scan_backoff_for_large_scan(self) -> None:
        first = self.client.post("/admin/index/scan")
        self.assertEqual(first.status_code, 200)

        second = self.client.post("/admin/index/scan")
        self.assertEqual(second.status_code, 429)
        body = second.json()
        self.assertEqual(body["status"], "backoff")
        self.assertGreater(body.get("retry_after_seconds", 0), 0)
        self.assertIsNotNone(body.get("backoff_until"))

    def _write_file(self, path: Path, payload: bytes) -> None:
        path.write_bytes(payload)


if __name__ == "__main__":
    unittest.main()
