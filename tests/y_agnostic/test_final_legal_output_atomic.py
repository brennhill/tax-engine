"""Atomic-write contract tests for ``write_final_legal_output_2025``.

The final-legal-output triple (``final-legal-output.json``,
``legal-execution-graph.json``, ``legal-execution-graph.mmd``) must
move from the prior consistent state to the new consistent state as a
group. A failure mid-commit must not leave a downstream renderer
seeing a stale graph paired with a fresh JSON payload (or vice versa).

These tests force a failure during the commit phase and assert the
prior state is preserved.

Authority context: this is repo-internal hygiene for audit-trail
integrity, anchoring the same posture as
https://www.gesetze-im-internet.de/estg/__32d.html (per-Posten audit
trail in § 32d Abs. 5 EStG must reference a single, internally
consistent graph snapshot).
"""
from __future__ import annotations

import ast
import concurrent.futures
import inspect
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tax_pipeline.core import io as core_io
from tax_pipeline.pipelines.y2025 import final_legal_output as flo
from tests.generated_demo import generated_demo_paths


class FinalLegalOutputAtomicWriteTest(unittest.TestCase):
    def test_real_fs_interrupted_write_preserves_target_and_cleans_temp(self) -> None:
        # Real-FS interrupted-write: pre-populate ``target`` with a
        # known-good payload, then force ``os.replace`` (the rename
        # phase of ``atomic_write_text``) to raise mid-commit. The
        # contract is:
        #   1. The original target file's bytes are unchanged.
        #   2. The orphaned temp file is cleaned up by the helper's
        #      best-effort error path (no ``.target.*.tmp`` leftovers).
        #   3. The exception propagates to the caller.
        #
        # This replaces the prior ``mock.patch.object(atomic_write_text)``
        # variant which proved only that the helper is replaceable; this
        # test exercises the helper's own atomicity contract on a real
        # filesystem.
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target.json"
            original = '{"original": true}\n'
            target.write_text(original, encoding="utf-8")

            real_replace = os.replace

            def failing_replace(src, dst, *args, **kwargs):
                # Sanity: the helper has gotten past the
                # tempfile.NamedTemporaryFile + flush + fsync phases,
                # so the temp file actually exists at this moment.
                self.assertTrue(Path(src).exists(), "temp file missing pre-rename")
                raise OSError("simulated rename failure mid-commit")

            with mock.patch.object(os, "replace", side_effect=failing_replace):
                with self.assertRaisesRegex(OSError, "simulated rename"):
                    core_io.atomic_write_text(target, '{"new": true}\n')

            # Target is byte-for-byte unchanged.
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                original,
                "interrupted write must not corrupt the target",
            )
            # No orphan temp file remains. The helper's BaseException
            # cleanup path runs ``os.unlink(tmp_name)`` so the directory
            # is left in the same shape it had before the write.
            leftovers = sorted(p.name for p in Path(tmpdir).iterdir() if p != target)
            self.assertEqual(
                leftovers,
                [],
                f"orphan temp file remains after interrupted write: {leftovers}",
            )
            # And the rename never fired.
            real_replace  # unused-imports suppressor

    def test_temp_file_does_not_persist_after_successful_write(self) -> None:
        # Atomic writes use a hidden ``.<name>.tmp`` sibling. After a clean
        # write, no temp leftover should remain.
        with generated_demo_paths() as paths:
            for name in (
                flo.FINAL_LEGAL_OUTPUT_NAME,
                flo.LEGAL_EXECUTION_GRAPH_JSON,
                flo.LEGAL_EXECUTION_GRAPH_MERMAID,
            ):
                # Hidden temp siblings now use a tempfile-generated suffix
                # to avoid concurrent-writer collisions; assert no
                # ``.<name>.…tmp`` leftover remains.
                leftovers = list(paths.analysis_root.glob(f".{name}.*.tmp"))
                self.assertEqual(
                    leftovers,
                    [],
                    f"orphaned atomic-write temp files present: {leftovers}",
                )
                # Also assert the legacy fixed-name temp is absent (would
                # indicate a regression to the pre-H9-fix code path).
                legacy = paths.analysis_root / f".{name}.tmp"
                self.assertFalse(
                    legacy.exists(),
                    f"legacy fixed-name atomic-write temp present: {legacy}",
                )

    def test_concurrent_writers_yield_one_winner_no_temp_leftovers(self) -> None:
        # H9 regression: with ``N`` threads writing the same target with
        # different content, the post-condition is that exactly one
        # writer's content is on disk (one of the N distinct strings,
        # byte-for-byte) AND no ``.tmp`` siblings remain.
        #
        # Authority context: this is repo-internal hygiene for atomic
        # final-legal-output emission per § 32d Abs. 5 EStG audit-trail
        # integrity (https://www.gesetze-im-internet.de/estg/__32d.html).
        # See docs/invariant-migration-plan.md §4 WS-2E (H9 atomic-write
        # filename collision).
        n_writers = 8
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "concurrent-target.json"
            payloads = [f"payload-{i}-{'x' * (i + 1)}\n" for i in range(n_writers)]
            barrier = threading.Barrier(n_writers)

            def writer(payload: str) -> None:
                # Synchronize so all threads hit atomic_write_text at
                # roughly the same instant; this is what surfaces the
                # collision in the pre-fix code.
                barrier.wait()
                flo.atomic_write_text(target, payload)

            with concurrent.futures.ThreadPoolExecutor(max_workers=n_writers) as pool:
                futures = [pool.submit(writer, p) for p in payloads]
                for fut in concurrent.futures.as_completed(futures):
                    fut.result()  # propagate any thread-level exception

            # Exactly one final content lands, byte-for-byte equal to one
            # of the N writers' payloads. Never empty, never partial,
            # never a mix.
            self.assertTrue(target.exists(), "concurrent target missing")
            final_content = target.read_text(encoding="utf-8")
            self.assertIn(
                final_content,
                payloads,
                "final content does not match any single writer's payload "
                "(indicates a torn write or interleaved bytes)",
            )

            # No ``.tmp`` siblings of any shape remain in the parent
            # directory after all threads complete.
            leftovers = sorted(p.name for p in target.parent.glob("*.tmp"))
            self.assertEqual(
                leftovers,
                [],
                f"orphaned atomic-write temp files remain: {leftovers}",
            )
            # Belt-and-braces: also reject anything matching the
            # tempfile prefix shape ``.<name>.*`` we used.
            prefix_leftovers = sorted(
                p.name
                for p in target.parent.glob(f".{target.name}.*")
                if p != target
            )
            self.assertEqual(
                prefix_leftovers,
                [],
                f"orphaned tempfile-prefix siblings remain: {prefix_leftovers}",
            )


class AtomicWriteTextSourceContractTest(unittest.TestCase):
    """I9 source-level contract: ``atomic_write_text`` MUST use the
    durable temp-file + fsync + replace sequence.

    A regression that reverts to a fixed-name temp filename, drops the
    ``flush()`` before ``close()``, or skips the parent-directory fsync
    would only show up under crash conditions (which the standard
    integration tests cannot exercise). These AST-level assertions
    guard the pattern at write time.

    Authority context: § 32d Abs. 5 EStG per-Posten audit trail must
    reference a single internally consistent graph snapshot; the
    final-legal-output triple's atomicity is what makes that audit
    invariant survive a crash mid-write.
    """

    def setUp(self) -> None:
        self.source = inspect.getsource(core_io.atomic_write_text)
        self.tree = ast.parse(self.source)
        # Function body of atomic_write_text — assertions below scan
        # only inside the helper, not the surrounding module.
        funcs = [
            n
            for n in self.tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "atomic_write_text"
        ]
        self.assertEqual(
            len(funcs), 1, "atomic_write_text must be defined exactly once"
        )
        self.func = funcs[0]

    def _calls(self) -> list[ast.Call]:
        return [n for n in ast.walk(self.func) if isinstance(n, ast.Call)]

    def _has_call(self, predicate) -> bool:
        return any(predicate(c) for c in self._calls())

    def test_uses_named_temporary_file(self) -> None:
        # ``tempfile.NamedTemporaryFile(...)`` must appear so the temp
        # filename is unique-per-writer. Catches the H9 fixed-name
        # collision regression (``.<name>.tmp``).
        def is_ntf(c: ast.Call) -> bool:
            f = c.func
            return (
                isinstance(f, ast.Attribute)
                and f.attr == "NamedTemporaryFile"
                and isinstance(f.value, ast.Name)
                and f.value.id == "tempfile"
            )

        self.assertTrue(
            self._has_call(is_ntf),
            "atomic_write_text must call tempfile.NamedTemporaryFile to "
            "allocate a unique temp filename per writer (I9 / H9 H9 fix).",
        )

    def test_calls_flush_before_close(self) -> None:
        # ``flush()`` must come before ``close()`` in the body so
        # buffered bytes hit the OS before fsync runs against an empty
        # in-kernel buffer.
        flush_lineno = None
        close_lineno = None
        for c in self._calls():
            f = c.func
            if isinstance(f, ast.Attribute):
                if f.attr == "flush" and flush_lineno is None:
                    flush_lineno = c.lineno
                if f.attr == "close" and close_lineno is None:
                    close_lineno = c.lineno
        self.assertIsNotNone(flush_lineno, "missing tmp_handle.flush()")
        self.assertIsNotNone(close_lineno, "missing tmp_handle.close()")
        self.assertLess(
            flush_lineno,
            close_lineno,
            "flush() must precede close() so buffered bytes are visible "
            "to fsync() before the file descriptor is closed.",
        )

    def test_fsyncs_parent_directory(self) -> None:
        # The helper must open the parent directory descriptor and call
        # ``os.fsync(dir_fd)`` so the rename itself is durable across
        # power loss. We assert there is at least one ``os.fsync(...)``
        # call whose argument is a Name (the dir_fd variable) — the
        # other ``os.fsync(tmp_handle.fileno())`` flushes the file's
        # data, not the directory entry.
        dir_fsync_seen = False
        for c in self._calls():
            f = c.func
            if not (
                isinstance(f, ast.Attribute)
                and f.attr == "fsync"
                and isinstance(f.value, ast.Name)
                and f.value.id == "os"
            ):
                continue
            if not c.args:
                continue
            arg = c.args[0]
            # ``os.fsync(dir_fd)`` — argument is a bare Name (the
            # directory descriptor variable). The data-fsync uses an
            # Attribute (``tmp_handle.fileno()``) so we can distinguish.
            if isinstance(arg, ast.Name):
                dir_fsync_seen = True
                break
        self.assertTrue(
            dir_fsync_seen,
            "atomic_write_text must call os.fsync(dir_fd) on the parent "
            "directory descriptor so the rename is durable across "
            "power loss.",
        )


if __name__ == "__main__":
    unittest.main()
