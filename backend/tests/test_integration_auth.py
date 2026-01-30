from __future__ import annotations

import base64
import unittest

from fastapi.testclient import TestClient

from tests.integration_harness import IntegrationTestCase


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class AuthIntegrationTest(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = self.harness.make_app()
        self.client = TestClient(self.app)

    def test_register_and_login_flow(self) -> None:
        options_response = self.client.post(
            "/auth/webauthn/register/options", json={"display_name": "Owner"}
        )
        self.assertEqual(options_response.status_code, 200)
        options_payload = options_response.json()

        verify_payload = {
            "credential_id": _encode(b"cred-1"),
            "public_key": _encode(b"pubkey-1"),
            "sign_count": 0,
            "transports": ["internal"],
            "challenge": options_payload["challenge"],
            "user_handle": options_payload["user"]["id"],
        }
        verify_response = self.client.post(
            "/auth/webauthn/register/verify", json=verify_payload
        )
        self.assertEqual(verify_response.status_code, 200)

        login_options = self.client.post("/auth/webauthn/login/options")
        self.assertEqual(login_options.status_code, 200)
        login_payload = {
            "credential_id": _encode(b"cred-1"),
            "challenge": login_options.json()["challenge"],
            "sign_count": 1,
        }
        login_response = self.client.post(
            "/auth/webauthn/login/verify", json=login_payload
        )
        self.assertEqual(login_response.status_code, 200)

        session_cookie = self.client.cookies.get(self.harness.config.session.cookie_name)
        self.assertIsNotNone(session_cookie)
        store = self.harness.make_session_store()
        self.assertIsNotNone(store.validate(session_cookie or ""))


if __name__ == "__main__":
    unittest.main()
