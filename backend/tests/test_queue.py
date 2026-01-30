import json
import unittest

from app.queue import (
    DEFAULT_QUEUE_NAME,
    InMemoryQueueBackend,
    InvalidJobError,
    Job,
    Queue,
    RedisQueueBackend,
    UnknownJobError,
    handle_noop,
    noop_job,
)


class FakeRedis:
    def __init__(self) -> None:
        self._items: list[object] = []

    def lpush(self, name: str, payload: object) -> None:
        del name
        self._items.insert(0, payload)

    def rpop(self, name: str) -> object | None:
        del name
        if not self._items:
            return None
        return self._items.pop()

    def brpop(self, name: str, timeout: int) -> tuple[str, object] | None:
        del timeout
        if not self._items:
            return None
        return (name, self._items.pop())


class QueueTest(unittest.TestCase):
    def test_noop_job_smoke(self) -> None:
        queue = Queue(InMemoryQueueBackend())
        queue.register(noop_job().name, handle_noop)

        queue.enqueue(noop_job())

        self.assertTrue(queue.process_next())
        self.assertFalse(queue.process_next())

    def test_register_validation(self) -> None:
        queue = Queue(InMemoryQueueBackend())
        with self.assertRaises(ValueError):
            queue.register("", handle_noop)
        queue.register("noop", handle_noop)
        with self.assertRaises(ValueError):
            queue.register("noop", handle_noop)

    def test_invalid_job_payloads(self) -> None:
        backend = InMemoryQueueBackend()
        queue = Queue(backend)

        backend.push(DEFAULT_QUEUE_NAME, "not-json")
        with self.assertRaises(InvalidJobError):
            queue.dequeue()

        backend.push(DEFAULT_QUEUE_NAME, json.dumps(["not", "dict"]))
        with self.assertRaises(InvalidJobError):
            queue.dequeue()

        backend.push(DEFAULT_QUEUE_NAME, json.dumps({"payload": {}}))
        with self.assertRaises(InvalidJobError):
            queue.dequeue()

    def test_unknown_job_handler(self) -> None:
        queue = Queue(InMemoryQueueBackend())
        queue.enqueue(Job(name="mystery", payload={}))

        with self.assertRaises(UnknownJobError):
            queue.process_next()

    def test_redis_backend_bytes_decode(self) -> None:
        fake = FakeRedis()
        backend = RedisQueueBackend(fake)  # type: ignore[arg-type]

        fake._items.append(b"payload")

        self.assertEqual(backend.pop(DEFAULT_QUEUE_NAME), "payload")

    def test_redis_backend_blocking_pop(self) -> None:
        fake = FakeRedis()
        backend = RedisQueueBackend(fake)  # type: ignore[arg-type]

        backend.push(DEFAULT_QUEUE_NAME, "payload")

        self.assertEqual(backend.pop(DEFAULT_QUEUE_NAME, timeout=1), "payload")
