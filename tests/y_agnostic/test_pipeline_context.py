from __future__ import annotations

import contextvars
import threading
import unittest

from tax_pipeline.pipeline_context import (
    clear_pipeline_context,
    get_pipeline_context_value,
    set_pipeline_context_value,
)


class PipelineContextTest(unittest.TestCase):
    """Pin the ContextVar-backed pipeline context behavior.

    The previous module-level mutable dict was Critical-1 in the code review
    (parallel runs corrupt each other). The ContextVar replacement must:
      1. Behave the same as a dict for the simple sequential case.
      2. Isolate per-thread / per-context writes so concurrent runs don't
         clobber each other.
    """

    def setUp(self) -> None:
        clear_pipeline_context()

    def test_set_and_get_round_trips_within_a_single_context(self) -> None:
        set_pipeline_context_value("k1", "v1")
        set_pipeline_context_value("k2", 42)
        self.assertEqual(get_pipeline_context_value("k1"), "v1")
        self.assertEqual(get_pipeline_context_value("k2"), 42)

    def test_get_returns_default_when_key_missing(self) -> None:
        self.assertIsNone(get_pipeline_context_value("missing"))
        self.assertEqual(get_pipeline_context_value("missing", default="dflt"), "dflt")

    def test_clear_pipeline_context_empties_current_dict(self) -> None:
        set_pipeline_context_value("k", "v")
        clear_pipeline_context()
        self.assertIsNone(get_pipeline_context_value("k"))

    def test_independent_contexts_do_not_clobber_each_other(self) -> None:
        # ContextVar isolation: two ``contextvars.copy_context()`` invocations
        # see independent dicts. This is the property that makes parallel runs
        # safe — the thing the prior implementation got wrong.
        clear_pipeline_context()

        def write_in_context_a() -> None:
            set_pipeline_context_value("shared_key", "context_a_value")

        def write_in_context_b() -> None:
            set_pipeline_context_value("shared_key", "context_b_value")

        ctx_a = contextvars.copy_context()
        ctx_b = contextvars.copy_context()

        ctx_a.run(write_in_context_a)
        ctx_b.run(write_in_context_b)

        # The outer (test) context never wrote `shared_key`, so it must still
        # be missing here. If the implementation were a module-level dict, the
        # last write (context_b) would leak into the outer context.
        self.assertIsNone(get_pipeline_context_value("shared_key"))

        # And each child context preserves its own value.
        self.assertEqual(
            ctx_a.run(lambda: get_pipeline_context_value("shared_key")),
            "context_a_value",
        )
        self.assertEqual(
            ctx_b.run(lambda: get_pipeline_context_value("shared_key")),
            "context_b_value",
        )

    def test_threads_do_not_clobber_each_other(self) -> None:
        # Threads inherit the ContextVar binding at creation but writes from
        # one thread are confined to that thread's view. This is the
        # concurrency-safety property the prior module-level dict lacked.
        clear_pipeline_context()
        results: dict[str, str | None] = {}

        def thread_body(label: str) -> None:
            # Each thread starts from its inherited (empty) view, writes its
            # own key, and reads it back.
            set_pipeline_context_value(f"thread_{label}", f"value_{label}")
            results[label] = get_pipeline_context_value(f"thread_{label}")

        threads = [
            threading.Thread(target=thread_body, args=(label,))
            for label in ("a", "b", "c", "d")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for label in ("a", "b", "c", "d"):
            self.assertEqual(results[label], f"value_{label}")

        # The main test thread did not write anything after clearing, so it
        # still sees an empty context (no leak from worker threads).
        for label in ("a", "b", "c", "d"):
            self.assertIsNone(get_pipeline_context_value(f"thread_{label}"))


if __name__ == "__main__":
    unittest.main()
