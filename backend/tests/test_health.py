import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import load_config


class HealthEndpointTest(unittest.TestCase):
    def test_health_returns_expected_payload(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config({"DATA_ROOT": root, "APP_ENV": "test"})
            app = create_app(config)

        client = TestClient(app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "env": "test"})
