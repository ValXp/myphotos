import base64
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.api.app import create_app
from app.auth.sessions import InMemorySessionStore
from app.auth.webauthn import (
    DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
    InMemoryRegistrationChallengeStore,
)
from app.config import load_config
from app.db.base import Base
from app.db.models import PasskeyCredential, User
from app.db.session import create_engine_from_config, create_session_factory


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class RegistrationVerifyTest(unittest.TestCase):
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
        self.registration_store = InMemoryRegistrationChallengeStore(
            default_ttl_seconds=DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS
        )
        self.session_store = InMemorySessionStore(default_ttl_seconds=300)
        self.app = create_app(
            self.config,
            registration_store=self.registration_store,
            session_store=self.session_store,
            db_session_factory=self.session_factory,
        )
        self.client = TestClient(self.app)

    def test_registration_verify_creates_user_and_passkey(self) -> None:
        options_response = self.client.post(
            "/auth/webauthn/register/options", json={"display_name": "Owner"}
        )
        self.assertEqual(options_response.status_code, 200)
        options_payload = options_response.json()

        verify_payload = {
            "credential": {
                "id": _encode(b"cred-1"),
                "rawId": _encode(b"cred-1"),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _encode(b"client"),
                    "attestationObject": _encode(b"attest"),
                },
            },
            "transports": ["internal"],
        }

        with patch(
            "app.api.webauthn.verify_registration_response",
            autospec=True,
        ) as verify_mock:
            verify_mock.return_value = type(
                "Verified",
                (),
                {
                    "credential_id": b"cred-1",
                    "credential_public_key": b"pubkey-1",
                    "sign_count": 0,
                },
            )()
            verify_response = self.client.post(
                "/auth/webauthn/register/verify", json=verify_payload
            )
        self.assertEqual(verify_response.status_code, 200)
        body = verify_response.json()
        self.assertEqual(body["status"], "ok")

        with self.session_factory() as db:
            user = db.execute(select(User)).scalar_one()
            self.assertEqual(user.display_name, "Owner")
            passkey = db.execute(select(PasskeyCredential)).scalar_one()
            self.assertEqual(passkey.user_id, user.id)
            self.assertEqual(passkey.sign_count, 0)
            self.assertEqual(passkey.transports, ["internal"])

    def test_registration_verify_rejects_invalid_challenge(self) -> None:
        options_response = self.client.post(
            "/auth/webauthn/register/options", json={"display_name": "Owner"}
        )
        self.assertEqual(options_response.status_code, 200)
        options_payload = options_response.json()

        verify_payload = {
            "credential": {
                "id": _encode(b"cred-2"),
                "rawId": _encode(b"cred-2"),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _encode(b"client"),
                    "attestationObject": _encode(b"attest"),
                },
            },
            "transports": None,
        }

        with patch(
            "app.api.webauthn.verify_registration_response",
            autospec=True,
            side_effect=Exception("registration challenge mismatch"),
        ):
            verify_response = self.client.post(
                "/auth/webauthn/register/verify", json=verify_payload
            )
        self.assertEqual(verify_response.status_code, 400)

        with self.session_factory() as db:
            user = db.execute(select(User)).scalar_one_or_none()
            self.assertIsNone(user)

    def test_registration_verify_requires_owner_session_when_registered(self) -> None:
        options_response = self.client.post(
            "/auth/webauthn/register/options", json={"display_name": "Owner"}
        )
        self.assertEqual(options_response.status_code, 200)
        options_payload = options_response.json()
        first_payload = {
            "credential": {
                "id": _encode(b"cred-first"),
                "rawId": _encode(b"cred-first"),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _encode(b"client"),
                    "attestationObject": _encode(b"attest"),
                },
            },
            "transports": ["internal"],
        }
        with patch(
            "app.api.webauthn.verify_registration_response",
            autospec=True,
        ) as verify_mock:
            verify_mock.return_value = type(
                "Verified",
                (),
                {
                    "credential_id": b"cred-first",
                    "credential_public_key": b"pubkey-first",
                    "sign_count": 1,
                },
            )()
            first_response = self.client.post(
                "/auth/webauthn/register/verify", json=first_payload
            )
        self.assertEqual(first_response.status_code, 200)

        second_options = self.client.post(
            "/auth/webauthn/register/options", json={"display_name": "Owner"}
        )
        self.assertEqual(second_options.status_code, 200)
        second_payload = {
            "credential": {
                "id": _encode(b"cred-second"),
                "rawId": _encode(b"cred-second"),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _encode(b"client"),
                    "attestationObject": _encode(b"attest"),
                },
            },
            "transports": ["usb"],
        }
        with patch(
            "app.api.webauthn.verify_registration_response",
            autospec=True,
        ) as verify_mock:
            verify_mock.return_value = type(
                "Verified",
                (),
                {
                    "credential_id": b"cred-second",
                    "credential_public_key": b"pubkey-second",
                    "sign_count": 0,
                },
            )()
            blocked_response = self.client.post(
                "/auth/webauthn/register/verify", json=second_payload
            )
        self.assertEqual(blocked_response.status_code, 401)

        with self.session_factory() as db:
            user = db.execute(select(User)).scalar_one()
            session = self.session_store.create(user.id)

        self.client.cookies.set(self.config.session.cookie_name, session.id)
        with patch(
            "app.api.webauthn.verify_registration_response",
            autospec=True,
        ) as verify_mock:
            verify_mock.return_value = type(
                "Verified",
                (),
                {
                    "credential_id": b"cred-second",
                    "credential_public_key": b"pubkey-second",
                    "sign_count": 0,
                },
            )()
            success_response = self.client.post(
                "/auth/webauthn/register/verify", json=second_payload
            )
        self.assertEqual(success_response.status_code, 200)

        with self.session_factory() as db:
            passkeys = db.execute(select(PasskeyCredential)).scalars().all()
            self.assertEqual(len(passkeys), 2)
