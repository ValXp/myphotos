import tempfile
import unittest

from fastapi import Request
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import load_config


class ProxyHeadersTest(unittest.TestCase):
    def test_forwarded_headers_applied_for_trusted_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "APP_ENV": "test",
                    "TRUSTED_PROXY_IPS": "testclient",
                }
            )
            app = create_app(config)

        @app.get("/who")
        async def who(request: Request):
            return {"url": str(request.url)}

        client = TestClient(app)
        response = client.get(
            "/who",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "photos.local",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "https://photos.local/who")

    def test_forwarded_headers_ignored_for_untrusted_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config({"DATA_ROOT": root, "APP_ENV": "test"})
            app = create_app(config)

        @app.get("/who")
        async def who(request: Request):
            return {"url": str(request.url)}

        client = TestClient(app)
        response = client.get(
            "/who",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "photos.local",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "http://testserver/who")


if __name__ == "__main__":
    unittest.main()
