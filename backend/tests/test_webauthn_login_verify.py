import base64
import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
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


class LoginVerifyTest(unittest.TestCase):
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
        self.login_store = InMemoryLoginChallengeStore(
            default_ttl_seconds=DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS
        )
        self.session_store = InMemorySessionStore(default_ttl_seconds=300)
        self.app = create_app(
            self.config,
            login_store=self.login_store,
            session_store=self.session_store,
            db_session_factory=self.session_factory,
        )
        self.client = TestClient(self.app)

    def test_login_verify_creates_session_and_updates_sign_count(self) -> None:
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
                    sign_count=1,
                    transports=["internal"],
                )
            )
            db.commit()

        options_response = self.client.post("/auth/webauthn/login/options")
        self.assertEqual(options_response.status_code, 200)
        options_payload = options_response.json()
        login_session_id = options_response.cookies.get(DEFAULT_LOGIN_SESSION_COOKIE_NAME)
        self.assertIsNotNone(login_session_id)

        verify_payload = {
            "credential_id": _encode(b"cred-1"),
            "challenge": options_payload["challenge"],
            "sign_count": 2,
        }
        verify_response = self.client.post(
            "/auth/webauthn/login/verify", json=verify_payload
        )
        self.assertEqual(verify_response.status_code, 200)
        body = verify_response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["user_id"], user_id)

        session_id = verify_response.cookies.get(self.config.session.cookie_name)
        self.assertIsNotNone(session_id)
        assert session_id is not None
        session = self.session_store.validate(session_id)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.user_id, user_id)

        stored = self.login_store.load(login_session_id)
        self.assertIsNone(stored)

        with self.session_factory() as db:
            passkey = db.execute(
                select(PasskeyCredential).where(PasskeyCredential.user_id == user_id)
            ).scalar_one()
            self.assertEqual(passkey.sign_count, 2)

        set_cookies = verify_response.headers.get_list("set-cookie")
        session_cookie_header = None
        for header in set_cookies:
            if header.startswith(f"{self.config.session.cookie_name}="):
                session_cookie_header = header
                break
        self.assertIsNotNone(session_cookie_header)
        assert session_cookie_header is not None
        header_lower = session_cookie_header.lower()
        self.assertIn("httponly", header_lower)
        self.assertIn("samesite=lax", header_lower)
        self.assertNotIn("secure", header_lower)

    def test_login_verify_rejects_invalid_challenge(self) -> None:
        with self.session_factory() as db:
            user = User(display_name="Owner")
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(
                PasskeyCredential(
                    user_id=user_id,
                    credential_id=b"cred-2",
                    public_key=b"pubkey-2",
                    sign_count=1,
                    transports=None,
                )
            )
            db.commit()

        options_response = self.client.post("/auth/webauthn/login/options")
        self.assertEqual(options_response.status_code, 200)

        verify_payload = {
            "credential_id": _encode(b"cred-2"),
            "challenge": "not-the-challenge",
            "sign_count": 2,
        }
        verify_response = self.client.post(
            "/auth/webauthn/login/verify", json=verify_payload
        )
        self.assertEqual(verify_response.status_code, 400)
        self.assertIsNone(verify_response.cookies.get(self.config.session.cookie_name))

        with self.session_factory() as db:
            passkey = db.execute(
                select(PasskeyCredential).where(PasskeyCredential.user_id == user_id)
            ).scalar_one()
            self.assertEqual(passkey.sign_count, 1)
