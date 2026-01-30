from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import json
import secrets
from typing import Callable, Protocol
import uuid

import redis

from app.config import Config

DEFAULT_REGISTRATION_SESSION_COOKIE_NAME = "myphotos_webauthn_registration"
DEFAULT_REGISTRATION_PREFIX = "myphotos:webauthn:registration:"
DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS = 5 * 60
DEFAULT_REGISTRATION_TIMEOUT_MS = 60 * 1000
DEFAULT_LOGIN_SESSION_COOKIE_NAME = "myphotos_webauthn_login"
DEFAULT_LOGIN_PREFIX = "myphotos:webauthn:login:"
DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS = 5 * 60
DEFAULT_LOGIN_TIMEOUT_MS = 60 * 1000


class RegistrationChallengeError(RuntimeError):
    pass


class InvalidRegistrationChallengeError(RegistrationChallengeError):
    pass


class LoginChallengeError(RuntimeError):
    pass


class InvalidLoginChallengeError(LoginChallengeError):
    pass


@dataclass(frozen=True)
class RegistrationChallenge:
    challenge: str
    user_handle: str
    user_name: str
    created_at: datetime


class RegistrationChallengeStore(Protocol):
    def save(
        self, session_id: str, challenge: RegistrationChallenge, ttl_seconds: int | None = None
    ) -> None:
        ...

    def load(self, session_id: str) -> RegistrationChallenge | None:
        ...

    def consume(self, session_id: str) -> RegistrationChallenge | None:
        ...


@dataclass(frozen=True)
class LoginChallenge:
    challenge: str
    user_id: str
    created_at: datetime


class LoginChallengeStore(Protocol):
    def save(self, session_id: str, challenge: LoginChallenge, ttl_seconds: int | None = None) -> None:
        ...

    def load(self, session_id: str) -> LoginChallenge | None:
        ...

    def consume(self, session_id: str) -> LoginChallenge | None:
        ...


@dataclass(frozen=True)
class _ChallengeRecord:
    challenge: RegistrationChallenge
    expires_at: datetime


@dataclass(frozen=True)
class _LoginChallengeRecord:
    challenge: LoginChallenge
    expires_at: datetime


class InMemoryRegistrationChallengeStore:
    def __init__(
        self,
        *,
        default_ttl_seconds: int = DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds, "default_ttl_seconds")
        self._now_fn = now_fn or _utcnow
        self._items: dict[str, _ChallengeRecord] = {}

    def save(
        self, session_id: str, challenge: RegistrationChallenge, ttl_seconds: int | None = None
    ) -> None:
        session_id = _validate_session_id(session_id)
        challenge = _validate_challenge(challenge)
        ttl = _resolve_ttl(ttl_seconds, self._default_ttl_seconds)
        now = self._now_fn()
        self._items[session_id] = _ChallengeRecord(
            challenge=challenge,
            expires_at=now + timedelta(seconds=ttl),
        )

    def load(self, session_id: str) -> RegistrationChallenge | None:
        session_id = _validate_session_id(session_id)
        record = self._items.get(session_id)
        if record is None:
            return None
        if self._now_fn() >= record.expires_at:
            self._items.pop(session_id, None)
            return None
        return record.challenge

    def consume(self, session_id: str) -> RegistrationChallenge | None:
        session_id = _validate_session_id(session_id)
        challenge = self.load(session_id)
        if challenge is None:
            return None
        self._items.pop(session_id, None)
        return challenge


class InMemoryLoginChallengeStore:
    def __init__(
        self,
        *,
        default_ttl_seconds: int = DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds, "default_ttl_seconds")
        self._now_fn = now_fn or _utcnow
        self._items: dict[str, _LoginChallengeRecord] = {}

    def save(self, session_id: str, challenge: LoginChallenge, ttl_seconds: int | None = None) -> None:
        session_id = _validate_session_id(session_id)
        challenge = _validate_login_challenge(challenge)
        ttl = _resolve_ttl(ttl_seconds, self._default_ttl_seconds)
        now = self._now_fn()
        self._items[session_id] = _LoginChallengeRecord(
            challenge=challenge,
            expires_at=now + timedelta(seconds=ttl),
        )

    def load(self, session_id: str) -> LoginChallenge | None:
        session_id = _validate_session_id(session_id)
        record = self._items.get(session_id)
        if record is None:
            return None
        if self._now_fn() >= record.expires_at:
            self._items.pop(session_id, None)
            return None
        return record.challenge

    def consume(self, session_id: str) -> LoginChallenge | None:
        session_id = _validate_session_id(session_id)
        challenge = self.load(session_id)
        if challenge is None:
            return None
        self._items.pop(session_id, None)
        return challenge


class RedisRegistrationChallengeStore:
    def __init__(
        self,
        client: redis.Redis[str],
        *,
        prefix: str = DEFAULT_REGISTRATION_PREFIX,
        default_ttl_seconds: int = DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
    ) -> None:
        if not prefix:
            raise ValueError("registration challenge prefix must be non-empty")
        self._client = client
        self._prefix = prefix
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds, "default_ttl_seconds")

    def save(
        self, session_id: str, challenge: RegistrationChallenge, ttl_seconds: int | None = None
    ) -> None:
        session_id = _validate_session_id(session_id)
        challenge = _validate_challenge(challenge)
        ttl = _resolve_ttl(ttl_seconds, self._default_ttl_seconds)
        payload = _serialize_challenge(challenge)
        self._client.setex(self._key(session_id), ttl, payload)

    def load(self, session_id: str) -> RegistrationChallenge | None:
        session_id = _validate_session_id(session_id)
        payload = self._client.get(self._key(session_id))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode()
        return _deserialize_challenge(session_id, payload)

    def consume(self, session_id: str) -> RegistrationChallenge | None:
        session_id = _validate_session_id(session_id)
        challenge = self.load(session_id)
        if challenge is None:
            return None
        self._client.delete(self._key(session_id))
        return challenge

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"


class RedisLoginChallengeStore:
    def __init__(
        self,
        client: redis.Redis[str],
        *,
        prefix: str = DEFAULT_LOGIN_PREFIX,
        default_ttl_seconds: int = DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS,
    ) -> None:
        if not prefix:
            raise ValueError("login challenge prefix must be non-empty")
        self._client = client
        self._prefix = prefix
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds, "default_ttl_seconds")

    def save(self, session_id: str, challenge: LoginChallenge, ttl_seconds: int | None = None) -> None:
        session_id = _validate_session_id(session_id)
        challenge = _validate_login_challenge(challenge)
        ttl = _resolve_ttl(ttl_seconds, self._default_ttl_seconds)
        payload = _serialize_login_challenge(challenge)
        self._client.setex(self._key(session_id), ttl, payload)

    def load(self, session_id: str) -> LoginChallenge | None:
        session_id = _validate_session_id(session_id)
        payload = self._client.get(self._key(session_id))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode()
        return _deserialize_login_challenge(session_id, payload)

    def consume(self, session_id: str) -> LoginChallenge | None:
        session_id = _validate_session_id(session_id)
        challenge = self.load(session_id)
        if challenge is None:
            return None
        self._client.delete(self._key(session_id))
        return challenge

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"


def create_registration_store(
    config: Config,
    *,
    client: redis.Redis[str] | None = None,
    prefix: str = DEFAULT_REGISTRATION_PREFIX,
    default_ttl_seconds: int = DEFAULT_REGISTRATION_CHALLENGE_TTL_SECONDS,
) -> RegistrationChallengeStore:
    resolved_client = client or redis.from_url(config.redis.url, decode_responses=True)
    return RedisRegistrationChallengeStore(
        resolved_client,
        prefix=prefix,
        default_ttl_seconds=default_ttl_seconds,
    )


def create_login_store(
    config: Config,
    *,
    client: redis.Redis[str] | None = None,
    prefix: str = DEFAULT_LOGIN_PREFIX,
    default_ttl_seconds: int = DEFAULT_LOGIN_CHALLENGE_TTL_SECONDS,
) -> LoginChallengeStore:
    resolved_client = client or redis.from_url(config.redis.url, decode_responses=True)
    return RedisLoginChallengeStore(
        resolved_client,
        prefix=prefix,
        default_ttl_seconds=default_ttl_seconds,
    )


def generate_challenge() -> str:
    return _base64url_encode(secrets.token_bytes(32))


def generate_user_handle() -> str:
    return _base64url_encode(uuid.uuid4().bytes)


def _resolve_ttl(ttl_seconds: int | None, default_ttl_seconds: int) -> int:
    if ttl_seconds is None:
        return default_ttl_seconds
    return _validate_ttl(ttl_seconds, "ttl_seconds")


def _validate_ttl(value: int, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _validate_session_id(session_id: str) -> str:
    if not session_id.strip():
        raise ValueError("session_id must be non-empty")
    return session_id


def _validate_challenge(challenge: RegistrationChallenge) -> RegistrationChallenge:
    if not challenge.challenge.strip():
        raise ValueError("challenge must be non-empty")
    if not challenge.user_handle.strip():
        raise ValueError("user_handle must be non-empty")
    if not challenge.user_name.strip():
        raise ValueError("user_name must be non-empty")
    return challenge


def _validate_login_challenge(challenge: LoginChallenge) -> LoginChallenge:
    if not challenge.challenge.strip():
        raise ValueError("challenge must be non-empty")
    if not challenge.user_id.strip():
        raise ValueError("user_id must be non-empty")
    return challenge


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_challenge(challenge: RegistrationChallenge) -> str:
    return json.dumps(
        {
            "challenge": challenge.challenge,
            "user_handle": challenge.user_handle,
            "user_name": challenge.user_name,
            "created_at": challenge.created_at.isoformat(),
        },
        sort_keys=True,
    )


def _deserialize_challenge(session_id: str, payload: str) -> RegistrationChallenge:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InvalidRegistrationChallengeError("challenge payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InvalidRegistrationChallengeError("challenge payload must be a JSON object")
    challenge = data.get("challenge")
    user_handle = data.get("user_handle")
    user_name = data.get("user_name")
    created_at = data.get("created_at")
    if not isinstance(challenge, str) or not challenge.strip():
        raise InvalidRegistrationChallengeError("challenge payload missing challenge")
    if not isinstance(user_handle, str) or not user_handle.strip():
        raise InvalidRegistrationChallengeError("challenge payload missing user_handle")
    if not isinstance(user_name, str) or not user_name.strip():
        raise InvalidRegistrationChallengeError("challenge payload missing user_name")
    if not isinstance(created_at, str) or not created_at.strip():
        raise InvalidRegistrationChallengeError("challenge payload missing created_at")
    try:
        parsed_created_at = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise InvalidRegistrationChallengeError("challenge created_at is not valid ISO format") from exc
    if parsed_created_at.tzinfo is None:
        parsed_created_at = parsed_created_at.replace(tzinfo=timezone.utc)
    return RegistrationChallenge(
        challenge=challenge,
        user_handle=user_handle,
        user_name=user_name,
        created_at=parsed_created_at,
    )


def _serialize_login_challenge(challenge: LoginChallenge) -> str:
    return json.dumps(
        {
            "challenge": challenge.challenge,
            "user_id": challenge.user_id,
            "created_at": challenge.created_at.isoformat(),
        },
        sort_keys=True,
    )


def _deserialize_login_challenge(session_id: str, payload: str) -> LoginChallenge:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InvalidLoginChallengeError("challenge payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InvalidLoginChallengeError("challenge payload must be a JSON object")
    challenge = data.get("challenge")
    user_id = data.get("user_id")
    created_at = data.get("created_at")
    if not isinstance(challenge, str) or not challenge.strip():
        raise InvalidLoginChallengeError("challenge payload missing challenge")
    if not isinstance(user_id, str) or not user_id.strip():
        raise InvalidLoginChallengeError("challenge payload missing user_id")
    if not isinstance(created_at, str) or not created_at.strip():
        raise InvalidLoginChallengeError("challenge payload missing created_at")
    try:
        parsed_created_at = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise InvalidLoginChallengeError("challenge created_at is not valid ISO format") from exc
    if parsed_created_at.tzinfo is None:
        parsed_created_at = parsed_created_at.replace(tzinfo=timezone.utc)
    return LoginChallenge(
        challenge=challenge,
        user_id=user_id,
        created_at=parsed_created_at,
    )


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
