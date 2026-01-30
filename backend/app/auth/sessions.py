from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Callable, Protocol
import uuid

import redis

from app.config import Config

DEFAULT_SESSION_PREFIX = "myphotos:session:"


class SessionError(RuntimeError):
    pass


class InvalidSessionError(SessionError):
    pass


@dataclass(frozen=True)
class Session:
    id: str
    user_id: str
    created_at: datetime


class SessionStore(Protocol):
    def create(self, user_id: str, ttl_seconds: int | None = None) -> Session:
        ...

    def validate(self, session_id: str) -> Session | None:
        ...

    def revoke(self, session_id: str) -> None:
        ...


@dataclass(frozen=True)
class _SessionRecord:
    session: Session
    expires_at: datetime


class InMemorySessionStore:
    def __init__(
        self,
        *,
        default_ttl_seconds: int,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds, "default_ttl_seconds")
        self._now_fn = now_fn or _utcnow
        self._sessions: dict[str, _SessionRecord] = {}

    def create(self, user_id: str, ttl_seconds: int | None = None) -> Session:
        user_id = _validate_user_id(user_id)
        ttl = _resolve_ttl(ttl_seconds, self._default_ttl_seconds)
        now = self._now_fn()
        session = Session(id=_new_session_id(), user_id=user_id, created_at=now)
        self._sessions[session.id] = _SessionRecord(
            session=session,
            expires_at=now + timedelta(seconds=ttl),
        )
        return session

    def validate(self, session_id: str) -> Session | None:
        session_id = _validate_session_id(session_id)
        record = self._sessions.get(session_id)
        if record is None:
            return None
        if self._now_fn() >= record.expires_at:
            self._sessions.pop(session_id, None)
            return None
        return record.session

    def revoke(self, session_id: str) -> None:
        session_id = _validate_session_id(session_id)
        self._sessions.pop(session_id, None)


class RedisSessionStore:
    def __init__(
        self,
        client: redis.Redis[str],
        *,
        prefix: str = DEFAULT_SESSION_PREFIX,
        default_ttl_seconds: int,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if not prefix:
            raise ValueError("session prefix must be non-empty")
        self._client = client
        self._prefix = prefix
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds, "default_ttl_seconds")
        self._now_fn = now_fn or _utcnow

    def create(self, user_id: str, ttl_seconds: int | None = None) -> Session:
        user_id = _validate_user_id(user_id)
        ttl = _resolve_ttl(ttl_seconds, self._default_ttl_seconds)
        now = self._now_fn()
        session = Session(id=_new_session_id(), user_id=user_id, created_at=now)
        payload = _serialize_session(session)
        self._client.setex(self._key(session.id), ttl, payload)
        return session

    def validate(self, session_id: str) -> Session | None:
        session_id = _validate_session_id(session_id)
        payload = self._client.get(self._key(session_id))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode()
        return _deserialize_session(session_id, payload)

    def revoke(self, session_id: str) -> None:
        session_id = _validate_session_id(session_id)
        self._client.delete(self._key(session_id))

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"


def create_session_store(
    config: Config,
    *,
    client: redis.Redis[str] | None = None,
) -> SessionStore:
    resolved_client = client or redis.from_url(config.redis.url, decode_responses=True)
    return RedisSessionStore(
        resolved_client,
        default_ttl_seconds=config.session.ttl_seconds,
    )


def _resolve_ttl(ttl_seconds: int | None, default_ttl_seconds: int) -> int:
    if ttl_seconds is None:
        return default_ttl_seconds
    return _validate_ttl(ttl_seconds, "ttl_seconds")


def _validate_ttl(value: int, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _validate_user_id(user_id: str) -> str:
    if not user_id.strip():
        raise ValueError("user_id must be non-empty")
    return user_id


def _validate_session_id(session_id: str) -> str:
    if not session_id.strip():
        raise ValueError("session_id must be non-empty")
    return session_id


def _new_session_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_session(session: Session) -> str:
    return json.dumps(
        {
            "user_id": session.user_id,
            "created_at": session.created_at.isoformat(),
        },
        sort_keys=True,
    )


def _deserialize_session(session_id: str, payload: str) -> Session:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InvalidSessionError("session payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InvalidSessionError("session payload must be a JSON object")
    user_id = data.get("user_id")
    created_at = data.get("created_at")
    if not isinstance(user_id, str) or not user_id.strip():
        raise InvalidSessionError("session payload missing user_id")
    if not isinstance(created_at, str) or not created_at.strip():
        raise InvalidSessionError("session payload missing created_at")
    try:
        parsed_created_at = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise InvalidSessionError("session created_at is not valid ISO format") from exc
    if parsed_created_at.tzinfo is None:
        parsed_created_at = parsed_created_at.replace(tzinfo=timezone.utc)
    return Session(id=session_id, user_id=user_id, created_at=parsed_created_at)
