from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import logging
from typing import Any, Callable, Protocol
import uuid

import redis

from app.config import RedisConfig
from app.observability import job_context

DEFAULT_QUEUE_NAME = "myphotos:jobs"
NOOP_JOB_NAME = "noop"

logger = logging.getLogger("app.queue")

class QueueError(RuntimeError):
    pass


class InvalidJobError(QueueError):
    pass


class UnknownJobError(QueueError):
    pass


@dataclass(frozen=True)
class Job:
    name: str
    payload: dict[str, Any]
    id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "payload": self.payload}
        if self.id is not None:
            data["id"] = self.id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        name = data.get("name")
        payload = data.get("payload")
        job_id = data.get("id")
        if not isinstance(name, str) or not name.strip():
            raise InvalidJobError("job name must be a non-empty string")
        if not isinstance(payload, dict):
            raise InvalidJobError("job payload must be a dict")
        if job_id is None:
            parsed_id = None
        elif isinstance(job_id, str) and job_id.strip():
            parsed_id = job_id
        else:
            raise InvalidJobError("job id must be a non-empty string")
        return cls(name=name, payload=payload, id=parsed_id)


JobHandler = Callable[[Job], None]


class QueueBackend(Protocol):
    def push(self, queue_name: str, payload: str) -> None:
        ...

    def pop(self, queue_name: str, timeout: int | None = None) -> str | None:
        ...


class RedisQueueBackend:
    def __init__(self, client: redis.Redis[str]) -> None:
        self._client = client

    def push(self, queue_name: str, payload: str) -> None:
        self._client.lpush(queue_name, payload)

    def pop(self, queue_name: str, timeout: int | None = None) -> str | None:
        if timeout is None:
            payload = self._client.rpop(queue_name)
        else:
            result = self._client.brpop(queue_name, timeout=timeout)
            if result is None:
                return None
            _, payload = result
        if isinstance(payload, bytes):
            return payload.decode()
        return payload


class InMemoryQueueBackend:
    def __init__(self) -> None:
        self._queues: dict[str, deque[str]] = {}

    def push(self, queue_name: str, payload: str) -> None:
        queue = self._queues.setdefault(queue_name, deque())
        queue.appendleft(payload)

    def pop(self, queue_name: str, timeout: int | None = None) -> str | None:
        del timeout
        queue = self._queues.get(queue_name)
        if not queue:
            return None
        return queue.pop()


class Queue:
    def __init__(self, backend: QueueBackend, *, queue_name: str = DEFAULT_QUEUE_NAME) -> None:
        self._backend = backend
        self._queue_name = queue_name
        self._handlers: dict[str, JobHandler] = {}

    def register(self, name: str, handler: JobHandler) -> None:
        if not name.strip():
            raise ValueError("job name must be non-empty")
        if name in self._handlers:
            raise ValueError(f"handler already registered for {name}")
        self._handlers[name] = handler

    def enqueue(self, job: Job) -> None:
        job_with_id = _ensure_job_id(job)
        self._backend.push(self._queue_name, _serialize_job(job_with_id))

    def dequeue(self, timeout: int | None = None) -> Job | None:
        payload = self._backend.pop(self._queue_name, timeout=timeout)
        if payload is None:
            return None
        return _deserialize_job(payload)

    def process_next(self, timeout: int | None = None) -> bool:
        job = self.dequeue(timeout)
        if job is None:
            return False
        job = _ensure_job_id(job)
        handler = self._handlers.get(job.name)
        if handler is None:
            with job_context(job.id):
                logger.error(
                    "job.unknown",
                    extra={"job_name": job.name, "queue": self._queue_name},
                )
            raise UnknownJobError(f"no handler registered for {job.name}")
        with job_context(job.id):
            logger.info(
                "job.start",
                extra={"job_name": job.name, "queue": self._queue_name},
            )
            try:
                handler(job)
            except Exception:
                logger.exception(
                    "job.error",
                    extra={"job_name": job.name, "queue": self._queue_name},
                )
                raise
            logger.info(
                "job.complete",
                extra={"job_name": job.name, "queue": self._queue_name},
            )
        return True


def _serialize_job(job: Job) -> str:
    return json.dumps(job.as_dict(), sort_keys=True)


def _deserialize_job(payload: str) -> Job:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InvalidJobError("job payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InvalidJobError("job payload must be a JSON object")
    return Job.from_dict(data)


def _ensure_job_id(job: Job) -> Job:
    if job.id is None:
        return Job(name=job.name, payload=job.payload, id=str(uuid.uuid4()))
    return job


def create_redis_client(config: RedisConfig) -> redis.Redis[str]:
    return redis.from_url(config.url, decode_responses=True)


def noop_job() -> Job:
    return Job(name=NOOP_JOB_NAME, payload={})


def handle_noop(job: Job) -> None:
    del job


def register_noop(queue: Queue) -> None:
    queue.register(NOOP_JOB_NAME, handle_noop)
