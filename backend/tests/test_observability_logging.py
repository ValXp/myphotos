import json
import logging
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import load_config
from app.observability import JSONFormatter, REQUEST_ID_HEADER, configure_logging
from app.queue import InMemoryQueueBackend, Queue, handle_noop, noop_job


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


class ObservabilityLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = _CaptureHandler()
        self.handler.setFormatter(JSONFormatter())
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(self.handler)
        self.addCleanup(root.removeHandler, self.handler)

    def test_request_logging_includes_request_id(self) -> None:
        configure_logging("INFO")
        with tempfile.TemporaryDirectory() as root_dir:
            config = load_config({"DATA_ROOT": root_dir, "APP_ENV": "test"})
            app = create_app(config)
        client = TestClient(app)
        request_id = "req-123"

        response = client.get("/health", headers={REQUEST_ID_HEADER: request_id})

        self.assertEqual(response.status_code, 200)
        payloads = _parse_messages(self.handler.messages)
        matches = [
            payload
            for payload in payloads
            if payload.get("message") == "request.complete"
        ]
        self.assertTrue(matches)
        self.assertTrue(any(payload.get("request_id") == request_id for payload in matches))
        self.assertTrue(any(payload.get("correlation_id") == request_id for payload in matches))

    def test_job_logging_includes_job_id(self) -> None:
        configure_logging("INFO")
        queue = Queue(InMemoryQueueBackend())
        queue.register(noop_job().name, handle_noop)

        queue.enqueue(noop_job())
        queue.process_next()

        payloads = _parse_messages(self.handler.messages)
        matches = [
            payload
            for payload in payloads
            if payload.get("message") == "job.complete"
        ]
        self.assertTrue(matches)
        self.assertTrue(all(payload.get("job_id") for payload in matches))
        self.assertTrue(all(payload.get("correlation_id") for payload in matches))


def _parse_messages(messages: list[str]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for message in messages:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


if __name__ == "__main__":
    unittest.main()
