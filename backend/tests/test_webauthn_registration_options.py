import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.webauthn import (
    DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
    DEFAULT_REGISTRATION_SESSION_COOKIE_NAME,
    InMemoryRegistrationChallengeStore,
)
from app.config import load_config


class RegistrationOptionsTest(unittest.TestCase):
    def test_registration_options_persists_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            config = load_config(
                {
                    "DATA_ROOT": root,
                    "APP_ENV": "test",
                    "WEBAUTHN_RP_ID": "photos.local",
                    "WEBAUTHN_RP_NAME": "My Photos",
                }
            )
            store = InMemoryRegistrationChallengeStore(
                default_ttl_seconds=DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS
            )
            app = create_app(config, registration_store=store)

        client = TestClient(app)
        response = client.post(
            "/auth/webauthn/register/options", json={"display_name": "Owner"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["rp"]["id"], "photos.local")
        self.assertEqual(payload["rp"]["name"], "My Photos")

        session_id = response.cookies.get(DEFAULT_REGISTRATION_SESSION_COOKIE_NAME)
        self.assertIsNotNone(session_id)

        stored = store.load(session_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.challenge, payload["challenge"])
        self.assertEqual(stored.user_handle, payload["user"]["id"])
        self.assertEqual(stored.user_name, "Owner")
