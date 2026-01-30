from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import logging
from threading import Lock
from typing import Callable

logger = logging.getLogger("app.metrics")

MetricHook = Callable[[str, int, dict[str, str]], None]


@dataclass(frozen=True)
class MetricSample:
    name: str
    value: int
    tags: dict[str, str]


class MetricsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._hooks: list[MetricHook] = []

    def increment(self, name: str, value: int = 1, *, tags: dict[str, str] | None = None) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("metric name must be non-empty")
        if value == 0:
            return
        if value < 0:
            raise ValueError("metric value must be positive")
        tag_items = tuple(sorted((str(key), str(val)) for key, val in (tags or {}).items()))
        with self._lock:
            self._counters[(name, tag_items)] += value
            hooks = list(self._hooks)
        if hooks:
            tags_payload = dict(tag_items)
            for hook in hooks:
                try:
                    hook(name, value, tags_payload)
                except Exception:
                    logger.exception("metrics.hook_error", extra={"metric": name})

    def register_hook(self, hook: MetricHook) -> None:
        with self._lock:
            self._hooks.append(hook)

    def snapshot(self) -> list[MetricSample]:
        with self._lock:
            items = list(self._counters.items())
        samples = [
            MetricSample(name=name, value=value, tags=dict(tag_items))
            for (name, tag_items), value in items
        ]
        samples.sort(key=lambda sample: (sample.name, sorted(sample.tags.items())))
        return samples

    def get_count(self, name: str, tags: dict[str, str] | None = None) -> int:
        tag_items = tuple(sorted((str(key), str(val)) for key, val in (tags or {}).items()))
        with self._lock:
            return self._counters.get((name, tag_items), 0)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._hooks.clear()


metrics = MetricsStore()


def record_request(method: str, path: str, status_code: int | None) -> None:
    status = str(status_code) if status_code is not None else "error"
    metrics.increment(
        "api_requests_total",
        tags={"method": method, "path": path, "status": status},
    )


def record_job(name: str, status: str) -> None:
    metrics.increment(
        "jobs_processed_total",
        tags={"job_name": name, "status": status},
    )


def register_hook(hook: MetricHook) -> None:
    metrics.register_hook(hook)
