import unittest

from app.metrics import MetricsStore


class MetricsStoreTest(unittest.TestCase):
    def test_increment_validates_inputs(self) -> None:
        store = MetricsStore()
        with self.assertRaises(ValueError):
            store.increment("")
        with self.assertRaises(ValueError):
            store.increment("requests", value=-1)

        # value=0 is treated as a no-op.
        store.increment("requests", value=0)
        self.assertEqual(store.get_count("requests"), 0)

    def test_increment_sorts_tags(self) -> None:
        store = MetricsStore()
        store.increment("requests", tags={"b": "2", "a": "1"})
        store.increment("requests", tags={"a": "1", "b": "2"})
        self.assertEqual(store.get_count("requests", {"a": "1", "b": "2"}), 2)

        snapshot = store.snapshot()
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0].name, "requests")
        self.assertEqual(snapshot[0].tags, {"a": "1", "b": "2"})

    def test_hooks_receive_updates_and_hook_errors_do_not_break_increment(self) -> None:
        store = MetricsStore()
        captured: list[tuple[str, int, dict[str, str]]] = []

        def bad_hook(name: str, value: int, tags: dict[str, str]) -> None:
            raise RuntimeError("boom")

        def good_hook(name: str, value: int, tags: dict[str, str]) -> None:
            captured.append((name, value, dict(tags)))

        store.register_hook(bad_hook)
        store.register_hook(good_hook)

        # Hook failures are logged and ignored.
        store.increment("requests", tags={"method": "GET"})

        self.assertEqual(store.get_count("requests", {"method": "GET"}), 1)
        self.assertEqual(captured, [("requests", 1, {"method": "GET"})])

    def test_reset_clears_counts_and_hooks(self) -> None:
        store = MetricsStore()
        store.register_hook(lambda *_: None)
        store.increment("requests")
        store.reset()
        self.assertEqual(store.get_count("requests"), 0)
        self.assertEqual(store.snapshot(), [])


if __name__ == "__main__":
    unittest.main()
