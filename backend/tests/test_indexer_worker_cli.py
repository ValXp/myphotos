import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ingest.watcher import WatchEvent, WatchEventKind
from workers import indexer
from workers.indexer import IndexerRunner


class IndexerRunnerUnitTest(unittest.TestCase):
    def test_should_scan_respects_interval_and_last_scan(self) -> None:
        queue = MagicMock()
        session = MagicMock()
        session_factory = MagicMock(return_value=session)
        runner = IndexerRunner(
            queue,
            session_factory,
            ["/tmp"],
            poll_interval_seconds=0,
            scan_interval_seconds=10,
        )

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        runner._last_scan_at = None
        self.assertTrue(runner._should_scan(now))

        runner._last_scan_at = now
        self.assertFalse(runner._should_scan(now + timedelta(seconds=9)))
        self.assertTrue(runner._should_scan(now + timedelta(seconds=10)))

        runner._scan_interval_seconds = 0
        self.assertFalse(runner._should_scan(now + timedelta(seconds=100)))

    def test_run_once_enqueues_scan_and_applies_events(self) -> None:
        queue = MagicMock()
        session = MagicMock()
        session_factory = MagicMock(return_value=session)
        runner = IndexerRunner(
            queue,
            session_factory,
            ["/tmp"],
            poll_interval_seconds=0,
            scan_interval_seconds=10,
            now_fn=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        runner._watcher = MagicMock()
        runner._watcher.poll.return_value = [
            WatchEvent(kind=WatchEventKind.add, paths=(Path("/tmp/photo.jpg"),))
        ]

        with patch.object(indexer, "enqueue_scan_jobs") as enqueue_scan_jobs, patch.object(
            indexer, "apply_watch_events"
        ) as apply_watch_events:
            did_work = runner.run_once(force_scan=True)

        self.assertTrue(did_work)
        enqueue_scan_jobs.assert_called_once()
        apply_watch_events.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()

    def test_run_forever_logs_and_continues_after_errors(self) -> None:
        queue = MagicMock()
        session_factory = MagicMock(return_value=MagicMock())
        slept: list[float] = []

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            raise StopIteration

        runner = IndexerRunner(
            queue,
            session_factory,
            ["/tmp"],
            poll_interval_seconds=123,
            scan_interval_seconds=0,
            sleep_fn=fake_sleep,
        )

        with patch.object(runner, "run_once", side_effect=RuntimeError("boom")):
            with self.assertRaises(StopIteration):
                runner.run_forever()

        self.assertEqual(slept, [123])


class IndexerCliTest(unittest.TestCase):
    def test_parse_roots_prefers_cli_over_config(self) -> None:
        config = SimpleNamespace(paths=SimpleNamespace(originals="/from-config"))
        self.assertEqual(indexer._parse_roots(config, ["/a", "/b"]), ["/a", "/b"])
        self.assertEqual(indexer._parse_roots(config, None), ["/from-config"])

    def test_main_once_runs_and_disposes_engine(self) -> None:
        fake_engine = MagicMock()
        fake_session_factory = MagicMock()
        fake_queue = MagicMock()
        fake_config = SimpleNamespace(
            app=SimpleNamespace(log_level="INFO"),
            paths=SimpleNamespace(originals="/originals"),
            redis=SimpleNamespace(),
        )

        with patch.object(indexer, "load_config", return_value=fake_config), patch.object(
            indexer, "configure_logging"
        ), patch.object(indexer, "create_engine_from_config", return_value=fake_engine), patch.object(
            indexer, "create_session_factory", return_value=fake_session_factory
        ), patch.object(indexer, "create_redis_client"), patch.object(
            indexer, "RedisQueueBackend"
        ), patch.object(indexer, "Queue", return_value=fake_queue), patch.object(
            indexer, "IndexerRunner"
        ) as runner_cls:
            runner = MagicMock()
            runner_cls.return_value = runner
            result = indexer.main(["--once", "--scan"])

        self.assertEqual(result, 0)
        runner.run_once.assert_called_once_with(force_scan=True)
        fake_engine.dispose.assert_called_once()

    def test_main_runs_forever_until_keyboard_interrupt(self) -> None:
        fake_engine = MagicMock()
        fake_session_factory = MagicMock()
        fake_queue = MagicMock()
        fake_config = SimpleNamespace(
            app=SimpleNamespace(log_level="INFO"),
            paths=SimpleNamespace(originals="/originals"),
            redis=SimpleNamespace(),
        )

        with patch.object(indexer, "load_config", return_value=fake_config), patch.object(
            indexer, "configure_logging"
        ), patch.object(indexer, "create_engine_from_config", return_value=fake_engine), patch.object(
            indexer, "create_session_factory", return_value=fake_session_factory
        ), patch.object(indexer, "create_redis_client"), patch.object(
            indexer, "RedisQueueBackend"
        ), patch.object(indexer, "Queue", return_value=fake_queue), patch.object(
            indexer, "IndexerRunner"
        ) as runner_cls:
            runner = MagicMock()
            runner.run_forever.side_effect = KeyboardInterrupt
            runner_cls.return_value = runner
            result = indexer.main(["--scan"])

        self.assertEqual(result, 0)
        runner.run_once.assert_called_once_with(force_scan=True)
        runner.run_forever.assert_called_once()
        fake_engine.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
