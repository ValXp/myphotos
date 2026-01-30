import unittest
from datetime import datetime, timedelta, timezone

from app.auth.sessions import (
    DEFAULT_SESSION_PREFIX,
    InMemorySessionStore,
    InvalidSessionError,
    RedisSessionStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.items: dict[str, object] = {}
        self.setex_calls: list[tuple[str, int, object]] = []

    def setex(self, name: str, ttl: int, value: object) -> None:
        self.setex_calls.append((name, ttl, value))
        self.items[name] = value

    def get(self, name: str) -> object | None:
        return self.items.get(name)

    def delete(self, name: str) -> None:
        self.items.pop(name, None)


class SessionStoreTest(unittest.TestCase):
    def test_in_memory_session_lifecycle(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store = InMemorySessionStore(default_ttl_seconds=60, now_fn=lambda: now)

        session = store.create("user-1")

        self.assertEqual(session.user_id, "user-1")
        self.assertEqual(store.validate(session.id), session)

        store.revoke(session.id)

        self.assertIsNone(store.validate(session.id))

    def test_in_memory_session_expiry(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock = {"now": now}

        def now_fn() -> datetime:
            return clock["now"]

        store = InMemorySessionStore(default_ttl_seconds=10, now_fn=now_fn)
        session = store.create("user-1")

        clock["now"] = now + timedelta(seconds=11)

        self.assertIsNone(store.validate(session.id))

    def test_in_memory_session_validations(self) -> None:
        store = InMemorySessionStore(default_ttl_seconds=5)

        with self.assertRaises(ValueError):
            store.create(" ")
        with self.assertRaises(ValueError):
            store.validate(" ")
        with self.assertRaises(ValueError):
            store.revoke("")

    def test_redis_session_store_round_trip(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fake = FakeRedis()
        store = RedisSessionStore(
            fake,  # type: ignore[arg-type]
            default_ttl_seconds=30,
            now_fn=lambda: now,
        )

        session = store.create("user-2", ttl_seconds=45)

        self.assertTrue(session.id)
        self.assertEqual(fake.setex_calls[0][0], f"{DEFAULT_SESSION_PREFIX}{session.id}")
        self.assertEqual(fake.setex_calls[0][1], 45)
        self.assertEqual(store.validate(session.id), session)

        store.revoke(session.id)

        self.assertIsNone(store.validate(session.id))

    def test_redis_invalid_payload(self) -> None:
        fake = FakeRedis()
        store = RedisSessionStore(fake, default_ttl_seconds=30)  # type: ignore[arg-type]
        fake.items[f"{DEFAULT_SESSION_PREFIX}broken"] = "not-json"

        with self.assertRaises(InvalidSessionError):
            store.validate("broken")
