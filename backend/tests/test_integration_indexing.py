from __future__ import annotations

import unittest

from app.ingest.jobs import METADATA_JOB_NAME, THUMB_JOB_NAME, apply_watch_events
from app.ingest.watcher import FilesystemWatcher
from tests.integration_harness import IntegrationTestCase


class IndexingIntegrationTest(IntegrationTestCase):
    def test_watch_events_enqueue_jobs_in_redis(self) -> None:
        root = self.harness.config.paths.originals
        watcher = FilesystemWatcher([root])

        photo = root / "photo.jpg"
        photo.write_bytes(b"image")
        events = watcher.poll()

        queue = self.harness.make_queue()
        with self.harness.session_factory() as db:
            stats = apply_watch_events(db, events, queue)
            db.commit()

        self.assertEqual(stats.added, 1)
        self.assertEqual(stats.enqueued, 2)

        first = queue.dequeue()
        second = queue.dequeue()

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        names = {first.name, second.name}
        self.assertEqual(names, {METADATA_JOB_NAME, THUMB_JOB_NAME})


if __name__ == "__main__":
    unittest.main()
