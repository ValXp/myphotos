import base64
import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from app.api.app import create_app
from app.auth.webauthn import (
    DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS,
    DEFAULT_LOGIN_SESSION_COOKIE_NAME,
    InMemoryLoginChallengeStore,
)
from app.config import load_config
from app.db.base import Base
from app.db.models import PasskeyCredential, User
from app.db.session import create_engine_from_config, create_session_factory


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class LoginOptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = load_config(
            {
                "DATA_ROOT": self.temp_dir.name,
                "APP_ENV": "test",
                "DB_URL": f"sqlite+pysqlite:///{os.path.join(self.temp_dir.name, 'test.db')}",
                "WEBAUTHN_RP_ID": "photos.local",
            }
        )
        self.engine = create_engine_from_config(self.config)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.login_store = InMemoryLoginChallengeStore(
            default_ttl_seconds=DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS
        )
        self.app = create_app(
            self.config,
            login_store=self.login_store,
            db_session_factory=self.session_factory,
        )
        self.client = TestClient(self.app)

    def test_login_options_persists_challenge(self) -> None:
        with self.session_factory() as db:
            user = User(display_name="Owner")
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(
                PasskeyCredential(
                    user_id=user_id,
                    credential_id=b"cred-1",
                    public_key=b"pubkey-1",
                    sign_count=0,
                    transports=["internal"],
                )
            )
            db.commit()

        response = self.client.post("/auth/webauthn/login/options")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["rpId"], "photos.local")
        self.assertEqual(len(payload["allowCredentials"]), 1)
        self.assertEqual(payload["allowCredentials"][0]["id"], _encode(b"cred-1"))

        session_id = response.cookies.get(DEFAULT_LOGIN_SESSION_COOKIE_NAME)
        self.assertIsNotNone(session_id)

        stored = self.login_store.load(session_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.challenge, payload["challenge"])
        self.assertEqual(stored.user_id, user_id)

    def test_login_options_requires_owner(self) -> None:
        response = self.client.post("/auth/webauthn/login/options")

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"], "owner not registered")
