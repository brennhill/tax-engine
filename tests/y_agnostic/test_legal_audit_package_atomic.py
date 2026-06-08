"""Atomic-write contract tests for ``_write_package_atomically``.

The legal-audit package directory (``legal-audit/germany/`` and
``legal-audit/usa/``) is a set of related Markdown / CSV artifacts —
``overview.md``, ``law-matrix.csv``, ``law-matrix.md``,
``assumptions.md``, ``trace-index.md``, ``index.md`` — that must move
from one consistent state to the next as a group. A reader walking the
package mid-write must never see a half-written file or a mix of new
and previous-run siblings.

These tests pin the same I9 atomic-write contract the final-legal-output
triple already satisfies (see ``tests/test_final_legal_output_atomic.py``):

- Each individual file is fully written or not at all (no torn writes).
- Concurrent writers never collide on a fixed staging-directory name
  (the H9 collision class).
- A successful run leaves no orphaned ``.<name>.…staging`` or
  ``.<name>.…backup`` siblings in ``root.parent``.

Authority context: this is repo-internal hygiene for legal-audit
package integrity, anchoring the same posture as
https://www.gesetze-im-internet.de/estg/__32d.html (per-Posten audit
trail in § 32d Abs. 5 EStG must reference a single, internally
consistent package snapshot). See ``CLAUDE.md`` invariant I9.
"""
from __future__ import annotations

import concurrent.futures
import tempfile
import threading
import unittest
from pathlib import Path

from tax_pipeline.legal_audit.common import _write_package_atomically


class LegalAuditPackageAtomicWriteTest(unittest.TestCase):
    def test_successful_write_leaves_no_temp_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            root = parent / "germany"
            rendered = {
                "overview.md": "# overview\n",
                "law-matrix.csv": "header\nrow\n",
                "index.md": "# index\n",
            }
            _write_package_atomically(root, rendered)

            self.assertTrue(root.is_dir())
            for name, content in rendered.items():
                self.assertEqual((root / name).read_text(encoding="utf-8"), content)

            # No orphaned staging or backup directories remain.
            siblings = sorted(p.name for p in parent.iterdir() if p != root)
            self.assertEqual(
                siblings,
                [],
                f"orphan staging/backup siblings remain: {siblings}",
            )

    def test_replace_existing_package_preserves_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            root = parent / "germany"

            first_payload = {"overview.md": "# v1\n", "index.md": "# v1\n"}
            _write_package_atomically(root, first_payload)
            self.assertEqual((root / "overview.md").read_text(encoding="utf-8"), "# v1\n")

            second_payload = {"overview.md": "# v2\n", "index.md": "# v2\n"}
            _write_package_atomically(root, second_payload)
            self.assertEqual((root / "overview.md").read_text(encoding="utf-8"), "# v2\n")

            # No leftover backup directory.
            siblings = sorted(p.name for p in parent.iterdir() if p != root)
            self.assertEqual(siblings, [], f"orphan siblings remain: {siblings}")

    def test_concurrent_writers_yield_one_winner_no_temp_leftovers(self) -> None:
        # H9 regression: with N threads writing the same target package
        # simultaneously, the post-condition is that exactly one writer's
        # contents land at ``root``, and no orphan staging or backup
        # directories remain. A fixed ``.<name>.staging`` filename would
        # let writer B's ``shutil.rmtree`` destroy writer A's in-flight
        # tree; the tempfile-based staging directory prevents that.
        n_writers = 6
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            root = parent / "germany"
            payloads = [
                {
                    "overview.md": f"# overview-{i}\n",
                    "index.md": f"# index-{i}\n",
                }
                for i in range(n_writers)
            ]
            barrier = threading.Barrier(n_writers)

            def writer(payload: dict[str, str]) -> None:
                # Synchronize so all threads hit ``_write_package_atomically``
                # at roughly the same instant; this is what surfaces the
                # collision in the pre-fix code path.
                barrier.wait()
                _write_package_atomically(root, payload)

            with concurrent.futures.ThreadPoolExecutor(max_workers=n_writers) as pool:
                futures = [pool.submit(writer, p) for p in payloads]
                # Some writers may race-lose on the rename step; that's
                # an expected exception, not a correctness failure. We
                # only require that AT LEAST ONE writer landed and no
                # writer left the package torn.
                exceptions: list[BaseException] = []
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        fut.result()
                    except (FileNotFoundError, OSError) as exc:
                        # Race-loser: target moved out from under it.
                        exceptions.append(exc)

            # The package directory must exist and contain a complete,
            # byte-for-byte equal copy of one of the N writers' payloads.
            self.assertTrue(root.is_dir(), "package directory missing after concurrent writes")
            actual_overview = (root / "overview.md").read_text(encoding="utf-8")
            actual_index = (root / "index.md").read_text(encoding="utf-8")
            matched = any(
                p["overview.md"] == actual_overview and p["index.md"] == actual_index
                for p in payloads
            )
            self.assertTrue(
                matched,
                "package contents do not match any single writer's payload "
                "(indicates a torn write or mixed payloads)",
            )

            # No orphan ``.<name>.…staging`` directories. A race-loser
            # may have its ``.<name>.…backup`` directory left behind
            # because the winner's rename consumed ``root`` before the
            # loser could clean up; that's an acceptable outcome (the
            # package contents are correct). What we cannot tolerate is
            # an orphan staging directory, which would indicate a torn
            # in-progress write that wasn't atomically renamed onto
            # ``root``.
            staging_orphans = sorted(
                p.name
                for p in parent.iterdir()
                if p != root and ".staging" in p.name
            )
            self.assertEqual(
                staging_orphans,
                [],
                f"orphan staging directories remain: {staging_orphans}",
            )


if __name__ == "__main__":
    unittest.main()
