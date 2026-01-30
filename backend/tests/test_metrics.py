import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import load_config
from app.metrics import metrics, record_request, register_hook
from app.queue import InMemoryQueueBackend, Queue, handle_noop, noop_job


class MetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        metrics.reset()

    def test_request_counter_incremented(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            config = load_config({"DATA_ROOT": root_dir, "APP_ENV": "test"})
            app = create_app(config)
        client = TestClient(app)

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        count = metrics.get_count(
            "api_requests_total",
            {"method": "GET", "path": "/health", "status": "200"},
        )
        self.assertEqual(count, 1)

    def test_job_counter_incremented(self) -> None:
        queue = Queue(InMemoryQueueBackend())
        queue.register(noop_job().name, handle_noop)

        queue.enqueue(noop_job())
        self.assertTrue(queue.process_next())

        count = metrics.get_count(
            "jobs_processed_total",
            {"job_name": "noop", "status": "success"},
        )
        self.assertEqual(count, 1)

    def test_hook_receives_metric_updates(self) -> None:
        captured: list[tuple[str, int, dict[str, str]]] = []

        def hook(name: str, value: int, tags: dict[str, str]) -> None:
            captured.append((name, value, dict(tags)))

        register_hook(hook)

        record_request("GET", "/metrics", 200)

        self.assertTrue(captured)
        name, value, tags = captured[0]
        self.assertEqual(name, "api_requests_total")
        self.assertEqual(value, 1)
        self.assertEqual(tags.get("path"), "/metrics")


if __name__ == "__main__":
    unittest.main()
