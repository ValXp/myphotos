from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any, Iterator, TextIO

REQUEST_ID_HEADER = "X-Request-ID"

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_JOB_ID: ContextVar[str | None] = ContextVar("job_id", default=None)

_STRUCTURED_HANDLER_FLAG = "_myphotos_structured_handler"

_STANDARD_LOG_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
}


def configure_logging(level: str, *, stream: TextIO | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if _has_structured_handler(root):
        return
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JSONFormatter())
    setattr(handler, _STRUCTURED_HANDLER_FLAG, True)
    root.addHandler(handler)


def _has_structured_handler(logger: logging.Logger) -> bool:
    for handler in logger.handlers:
        if getattr(handler, _STRUCTURED_HANDLER_FLAG, False):
            return True
    return False


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def get_job_id() -> str | None:
    return _JOB_ID.get()


@contextmanager
def request_context(request_id: str | None) -> Iterator[None]:
    token = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)


@contextmanager
def job_context(job_id: str | None) -> Iterator[None]:
    token = _JOB_ID.set(job_id)
    try:
        yield
    finally:
        _JOB_ID.reset(token)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        job_id = get_job_id()
        if request_id:
            payload["request_id"] = request_id
        if job_id:
            payload["job_id"] = job_id
        if request_id or job_id:
            payload["correlation_id"] = request_id or job_id

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_KEYS
        }
        if extras:
            payload.update(extras)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)
