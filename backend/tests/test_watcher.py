import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.ingest.watcher import FilesystemWatcher, WatchEventKind


class FilesystemWatcherTest(unittest.TestCase):
    def test_emits_add_and_delete(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            photo = root / "photo.jpg"
            photo.write_bytes(b"image")
            resolved = photo.resolve(strict=False)

            watcher = FilesystemWatcher([root])
            events = watcher.poll()

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.kind, WatchEventKind.add)
            self.assertEqual(event.paths, (resolved,))

            photo.unlink()
            events = watcher.poll()

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.kind, WatchEventKind.delete)
            self.assertEqual(event.paths, (resolved,))

    def test_emits_move(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = root / "photo.jpg"
            original.write_bytes(b"image")
            original_resolved = original.resolve(strict=False)

            watcher = FilesystemWatcher([root])
            watcher.poll()

            moved = root / "renamed.jpg"
            original.rename(moved)
            moved_resolved = moved.resolve(strict=False)

            events = watcher.poll()

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.kind, WatchEventKind.move)
            self.assertEqual(event.previous_paths, (original_resolved,))
            self.assertEqual(event.paths, (moved_resolved,))

    def test_filters_unsupported(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            note = root / "notes.txt"
            note.write_text("ignore")

            watcher = FilesystemWatcher([root])
            events = watcher.poll()

            self.assertEqual(events, [])

    def test_groups_live_photo_pair_add_and_move(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            still = root / "IMG_0001.HEIC"
            video = root / "IMG_0001.MOV"
            still.write_bytes(b"still")
            video.write_bytes(b"video")
            still_resolved = still.resolve(strict=False)
            video_resolved = video.resolve(strict=False)

            watcher = FilesystemWatcher([root])
            events = watcher.poll()

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.kind, WatchEventKind.add)
            self.assertEqual(event.paths, (still_resolved, video_resolved))

            new_still = root / "IMG_0002.HEIC"
            new_video = root / "IMG_0002.MOV"
            still.rename(new_still)
            video.rename(new_video)
            new_still_resolved = new_still.resolve(strict=False)
            new_video_resolved = new_video.resolve(strict=False)

            events = watcher.poll()

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.kind, WatchEventKind.move)
            self.assertEqual(event.paths, (new_still_resolved, new_video_resolved))
            self.assertEqual(event.previous_paths, (still_resolved, video_resolved))


if __name__ == "__main__":
    unittest.main()
