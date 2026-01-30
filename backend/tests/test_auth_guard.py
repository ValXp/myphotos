import tempfile
import unittest

from fastapi import Depends
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.deps import require_owner_session
from app.auth.sessions import InMemorySessionStore, Session
from app.config import load_config


class AuthGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = load_config({"DATA_ROOT": self.temp_dir.name, "APP_ENV": "test"})
        self.session_store = InMemorySessionStore(default_ttl_seconds=300)
        self.app = create_app(self.config, session_store=self.session_store)

        @self.app.get("/protected")
        def protected(_: Session = Depends(require_owner_session)) -> dict[str, str]:
            return {"status": "ok"}

        self.client = TestClient(self.app)

    def test_owner_guard_requires_session(self) -> None:
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 401)

        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)

    def test_owner_guard_allows_session(self) -> None:
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.config.session.cookie_name, session.id)

        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
