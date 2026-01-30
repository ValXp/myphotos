import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.config import load_config


class LogoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = load_config({"DATA_ROOT": self.temp_dir.name, "APP_ENV": "test"})
        self.session_store = InMemorySessionStore(default_ttl_seconds=300)
        self.app = create_app(self.config, session_store=self.session_store)
        self.client = TestClient(self.app)

    def test_logout_revokes_session_and_clears_cookie(self) -> None:
        session = self.session_store.create("user-1")
        self.client.cookies.set(self.config.session.cookie_name, session.id)

        response = self.client.post("/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIsNone(self.session_store.validate(session.id))

        set_cookies = response.headers.get_list("set-cookie")
        session_cookie_header = None
        for header in set_cookies:
            if header.startswith(f"{self.config.session.cookie_name}="):
                session_cookie_header = header
                break
        self.assertIsNotNone(session_cookie_header)
        assert session_cookie_header is not None
        header_lower = session_cookie_header.lower()
        self.assertIn("max-age=0", header_lower)
        self.assertIn("httponly", header_lower)
        self.assertIn("samesite=lax", header_lower)
        self.assertNotIn("secure", header_lower)
