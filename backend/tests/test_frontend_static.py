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


class FrontendStaticTest(unittest.TestCase):
    def _create_client(self) -> TestClient:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        dist_dir = os.path.join(temp_dir.name, "dist")
        os.makedirs(dist_dir, exist_ok=True)
        index_path = os.path.join(dist_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as handle:
            handle.write("<html><body>MyPhotos</body></html>")

        assets_dir = os.path.join(dist_dir, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        asset_path = os.path.join(assets_dir, "app.js")
        with open(asset_path, "w", encoding="utf-8") as handle:
            handle.write("console.log('myphotos');")

        db_path = os.path.join(temp_dir.name, "test.db")
        config = load_config(
            {
                "DATA_ROOT": temp_dir.name,
                "APP_ENV": "test",
                "DB_URL": f"sqlite+pysqlite:///{db_path}",
                "FRONTEND_DIST_DIR": dist_dir,
            }
        )
        app = create_app(
            config,
            session_store=InMemorySessionStore(default_ttl_seconds=300),
            registration_store=InMemoryRegistrationChallengeStore(),
            login_store=InMemoryLoginChallengeStore(),
            queue=Queue(InMemoryQueueBackend()),
        )
        return TestClient(app)

    def test_spa_routes_and_api_routes(self) -> None:
        client = self._create_client()

        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("MyPhotos", response.text)

        share_response = client.get("/share/demo-token")
        self.assertEqual(share_response.status_code, 200)
        self.assertIn("MyPhotos", share_response.text)

        health_response = client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"status": "ok", "env": "test"})

    def test_static_assets_are_served(self) -> None:
        client = self._create_client()

        response = client.get("/assets/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("console.log", response.text)
