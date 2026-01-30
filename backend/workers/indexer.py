from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Callable, Iterable, Sequence

from sqlalchemy.orm import Session, sessionmaker

from app.config import Config, load_config
from app.db.session import create_engine_from_config, create_session_factory
from app.ingest.jobs import apply_watch_events, enqueue_scan_jobs
from app.ingest.watcher import FilesystemWatcher
from app.observability import configure_logging
from app.queue import Queue, RedisQueueBackend, create_redis_client

logger = logging.getLogger("app.workers.indexer")

DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_SCAN_INTERVAL_SECONDS = 3600

SleepFn = Callable[[float], None]
NowFn = Callable[[], datetime]


class IndexerRunner:
    def __init__(
        self,
        queue: Queue,
        session_factory: sessionmaker[Session],
        roots: Iterable[str | Path],
        *,
        follow_symlinks: bool = False,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        scan_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS,
        sleep_fn: SleepFn | None = None,
        now_fn: NowFn | None = None,
    ) -> None:
        self._queue = queue
        self._session_factory = session_factory
        self._roots = tuple(Path(root) for root in roots)
        self._follow_symlinks = follow_symlinks
        self._watcher = FilesystemWatcher(self._roots, follow_symlinks=follow_symlinks)
        self._poll_interval_seconds = poll_interval_seconds
        self._scan_interval_seconds = scan_interval_seconds
        self._sleep = sleep_fn or time.sleep
        self._now = now_fn or _utcnow
        self._last_scan_at: datetime | None = None

    def run_once(
        self,
        *,
        force_scan: bool = False,
        allow_scheduled_scan: bool = False,
    ) -> bool:
        did_work = False
        session = self._session_factory()
        try:
            now = self._now()
            if force_scan or (allow_scheduled_scan and self._should_scan(now)):
                enqueue_scan_jobs(
                    session,
                    self._roots,
                    self._queue,
                    follow_symlinks=self._follow_symlinks,
                )
                self._last_scan_at = now
                did_work = True
            events = self._watcher.poll()
            if events:
                apply_watch_events(session, events, self._queue)
                session.commit()
                did_work = True
            return did_work
        finally:
            session.close()

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once(allow_scheduled_scan=True)
            except Exception:
                logger.exception("indexer.poll_failed")
            self._sleep(self._poll_interval_seconds)

    def _should_scan(self, now: datetime) -> bool:
        if self._scan_interval_seconds <= 0:
            return False
        if self._last_scan_at is None:
            return True
        elapsed = (now - self._last_scan_at).total_seconds()
        return elapsed >= self._scan_interval_seconds


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_roots(
    config: Config, roots: Sequence[str] | None
) -> list[str | Path]:
    if roots:
        return list(roots)
    return [config.paths.originals]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indexer worker for myphotos")
    parser.add_argument(
        "--root",
        action="append",
        help="Watched root directory (repeatable). Defaults to originals dir.",
    )
    parser.add_argument("--once", action="store_true", help="Poll once and exit")
    parser.add_argument("--scan", action="store_true", help="Force a full scan")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds between watcher polls",
    )
    parser.add_argument(
        "--scan-interval",
        type=int,
        default=DEFAULT_SCAN_INTERVAL_SECONDS,
        help="Seconds between full scans (0 disables scheduled scans)",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinks when scanning and watching",
    )
    args = parser.parse_args(argv)

    config = load_config()
    configure_logging(config.app.log_level)
    roots = _parse_roots(config, args.root)

    engine = create_engine_from_config(config)
    session_factory = create_session_factory(engine)
    queue = Queue(RedisQueueBackend(create_redis_client(config.redis)))

    runner = IndexerRunner(
        queue,
        session_factory,
        roots,
        follow_symlinks=args.follow_symlinks,
        poll_interval_seconds=args.poll_interval,
        scan_interval_seconds=args.scan_interval,
    )

    if args.once:
        runner.run_once(force_scan=args.scan)
        engine.dispose()
        return 0

    try:
        if args.scan:
            runner.run_once(force_scan=True)
        runner.run_forever()
    except KeyboardInterrupt:
        logger.info("indexer.shutdown")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
