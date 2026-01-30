import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.auth.webauthn import (
    InMemoryLoginChallengeStore,
    InMemoryRegistrationChallengeStore,
)
from app.config import load_config
from app.queue import InMemoryQueueBackend, Queue


class FakeRedis:
    def __init__(self, *, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def ping(self) -> bool:
        if self._should_fail:
            raise RuntimeError("redis unavailable")
        return True


class ReadyEndpointTest(unittest.TestCase):
    def _create_client(self, *, redis_fail: bool = False) -> TestClient:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = os.path.join(temp_dir.name, "test.db")
        config = load_config(
            {
                "DATA_ROOT": temp_dir.name,
                "APP_ENV": "test",
                "DB_URL": f"sqlite+pysqlite:///{db_path}",
            }
        )
        app = create_app(
            config,
            session_store=InMemorySessionStore(default_ttl_seconds=300),
            registration_store=InMemoryRegistrationChallengeStore(),
            login_store=InMemoryLoginChallengeStore(),
            queue=Queue(InMemoryQueueBackend()),
        )
        app.state.redis_client = FakeRedis(should_fail=redis_fail)
        return TestClient(app)

    def test_ready_reports_dependencies_ready(self) -> None:
        client = self._create_client()
        response = client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "dependencies": {"db": "ok", "redis": "ok"},
            },
        )

    def test_ready_reports_dependency_failure(self) -> None:
        client = self._create_client(redis_fail=True)
        response = client.get("/ready")
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["dependencies"]["db"], "ok")
        self.assertEqual(payload["dependencies"]["redis"], "error")
