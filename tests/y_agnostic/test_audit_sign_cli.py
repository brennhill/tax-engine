"""Tests for ``python -m law.audit`` (proposal A4 + LOCK.md § 2 Layer 1).

The CLI hashes vetted statutory data files (``law/**/*.{py,toml}``) and
records the digests in ``.audit/hashes.toml`` so any subsequent edit
to a signed file is caught by ``make check-invariants``. These tests
exercise sign / verify / status against a temporary tree so the real
registry under ``$REPO/.audit/hashes.toml`` is never mutated.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from law import audit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_PY_FRONTMATTER_TEMPLATE = '''"""
---
jurisdiction: TEST
tax_year: 2025
statute: § X TestG
url: https://example.test/x
contains:
  - X
numeric_constants:
  - X_VALUE: 100
amended_by: []
audited_by: test
audited_on: 2026-05-09
audit_hash: pending
---
"""
from __future__ import annotations

X_VALUE = 100
'''

_TOML_TEMPLATE = """\
[X_VALUE]
value = "100"
authority = "§ X TestG"
citation_url = "https://example.test/x"
"""


def _make_test_tree(tmp: Path) -> tuple[Path, Path, Path]:
    """Build a minimal repo-shaped tree under ``tmp``.

    Returns ``(repo_root, py_path, toml_path)`` where ``py_path`` and
    ``toml_path`` are signable files under ``law/<juri>/year_2025/test/``.

    Also creates an empty ``tax_pipeline/law_spec/`` directory because
    the audit module's second signable root (slice W2.C / T3.3,
    2026-05-11) walks that tree. Leaving it absent means
    ``_signable_roots()`` skips it harmlessly; creating it empty makes
    discovery semantics explicit.
    """
    repo_root = tmp
    law_dir = repo_root / "law"
    test_dir = law_dir / "testjuri" / "year_2025" / "test"
    test_dir.mkdir(parents=True)
    # Empty law_spec/ — second signable root added by slice W2.C / T3.3.
    (repo_root / "tax_pipeline" / "law_spec").mkdir(parents=True)
    # __init__.py for package shape (excluded from signing per LOCK.md).
    (law_dir / "__init__.py").write_text("", encoding="utf-8")
    (law_dir / "testjuri" / "__init__.py").write_text("", encoding="utf-8")
    (law_dir / "testjuri" / "year_2025" / "__init__.py").write_text("", encoding="utf-8")
    (test_dir / "__init__.py").write_text("", encoding="utf-8")
    py_path = test_dir / "p1.py"
    toml_path = test_dir / "p1.toml"
    py_path.write_text(_PY_FRONTMATTER_TEMPLATE, encoding="utf-8")
    toml_path.write_text(_TOML_TEMPLATE, encoding="utf-8")
    return repo_root, py_path, toml_path


class AuditCliInTempTreeTest(unittest.TestCase):
    """Sign / verify / status against a temp tree, never the real repo."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        # Resolve so /var → /private/var on macOS matches what
        # ``Path.resolve()`` returns inside the CLI; otherwise the
        # ``relative_to(LAW_DIR)`` check rejects every path.
        self.tmp = Path(self._tmpdir.name).resolve()
        self.repo_root, self.py_path, self.toml_path = _make_test_tree(self.tmp)
        # Patch module-level path constants to point at the temp tree.
        # LAW_SPEC_DIR is the second signable root (slice W2.C / T3.3,
        # 2026-05-11); the temp tree provides an empty directory at the
        # patched location so discovery doesn't sweep in the real
        # repo's law-spec markdown.
        self._patches = [
            mock.patch.object(audit, "REPO_ROOT", self.repo_root),
            mock.patch.object(audit, "LAW_DIR", self.repo_root / "law"),
            mock.patch.object(
                audit,
                "LAW_SPEC_DIR",
                self.repo_root / "tax_pipeline" / "law_spec",
            ),
            mock.patch.object(
                audit,
                "REGISTRY_PATH",
                self.repo_root / ".audit" / "hashes.toml",
            ),
            # Force the never-sign list to NOT match anything in our temp
            # tree (audit.py / _utils paths don't exist in the test tree
            # but the resolution logic still runs).
            mock.patch.object(audit, "_NEVER_SIGN_REL_PATHS", ()),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Hashing semantics
    # ------------------------------------------------------------------

    def test_compute_hash_normalises_audit_hash_line_in_py(self) -> None:
        """Updating ``audit_hash:`` in a .py must NOT change its digest."""
        digest_before = audit.compute_hash(self.py_path)
        # Simulate the sign step rewriting the marker.
        text = self.py_path.read_text(encoding="utf-8")
        text2 = text.replace("audit_hash: pending", f"audit_hash: sha256:{digest_before}")
        self.py_path.write_text(text2, encoding="utf-8")
        digest_after = audit.compute_hash(self.py_path)
        self.assertEqual(digest_before, digest_after)

    def test_compute_hash_changes_on_body_edit(self) -> None:
        """Any body edit (numeric value, comment) MUST change the digest."""
        digest_before = audit.compute_hash(self.py_path)
        text = self.py_path.read_text(encoding="utf-8")
        self.py_path.write_text(text.replace("X_VALUE = 100", "X_VALUE = 999"), encoding="utf-8")
        digest_after = audit.compute_hash(self.py_path)
        self.assertNotEqual(digest_before, digest_after)

    def test_compute_hash_changes_on_toml_edit(self) -> None:
        """Any TOML byte change (e.g. statutory value) MUST change digest."""
        digest_before = audit.compute_hash(self.toml_path)
        text = self.toml_path.read_text(encoding="utf-8")
        self.toml_path.write_text(text.replace('"100"', '"999"'), encoding="utf-8")
        digest_after = audit.compute_hash(self.toml_path)
        self.assertNotEqual(digest_before, digest_after)

    # ------------------------------------------------------------------
    # CLI: sign / verify / status round-trip
    # ------------------------------------------------------------------

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = audit.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_sign_then_verify_passes(self) -> None:
        rc, _, _ = self._run(["sign", str(self.py_path), str(self.toml_path)])
        self.assertEqual(rc, 0)
        rc, stdout, _ = self._run(["verify"])
        self.assertEqual(rc, 0)
        self.assertIn("OK", stdout)
        self.assertIn("2 signed file(s)", stdout)

    def test_sign_writes_registry_with_required_fields(self) -> None:
        self._run(["sign", str(self.py_path), str(self.toml_path)])
        registry = self.repo_root / ".audit" / "hashes.toml"
        self.assertTrue(registry.exists(), "registry must be created by sign")
        data = tomllib.loads(registry.read_text(encoding="utf-8"))
        # Every signed entry must carry hash + audited_by + audited_on
        # per LOCK.md § 2 Layer 1.
        for rel, entry in data.items():
            with self.subTest(path=rel):
                self.assertTrue(entry["hash"].startswith("sha256:"))
                self.assertEqual(len(entry["hash"]), len("sha256:") + 64)
                self.assertTrue(entry["audited_by"])
                self.assertTrue(entry["audited_on"])

    def test_sign_updates_in_file_audit_hash_marker(self) -> None:
        rc, _, _ = self._run(["sign", str(self.py_path)])
        self.assertEqual(rc, 0)
        text = self.py_path.read_text(encoding="utf-8")
        self.assertNotIn("audit_hash: pending", text)
        # The frontmatter marker now records the actual digest.
        registry = tomllib.loads(
            (self.repo_root / ".audit" / "hashes.toml").read_text(encoding="utf-8")
        )
        rel = "law/testjuri/year_2025/test/p1.py"
        self.assertIn(rel, registry)
        registered = registry[rel]["hash"]
        self.assertIn(registered, text)

    def test_sign_idempotent(self) -> None:
        """Signing the same file twice yields the same hash; second sign
        does not flip the registry hash to a different value."""
        self._run(["sign", str(self.py_path)])
        first = tomllib.loads(
            (self.repo_root / ".audit" / "hashes.toml").read_text(encoding="utf-8")
        )
        self._run(["sign", str(self.py_path)])
        second = tomllib.loads(
            (self.repo_root / ".audit" / "hashes.toml").read_text(encoding="utf-8")
        )
        rel = "law/testjuri/year_2025/test/p1.py"
        self.assertEqual(first[rel]["hash"], second[rel]["hash"])

    def test_verify_fails_when_signed_file_is_modified(self) -> None:
        rc, _, _ = self._run(["sign", str(self.py_path), str(self.toml_path)])
        self.assertEqual(rc, 0)
        # Mutate the TOML "value" field (the highest-impact drift case).
        text = self.toml_path.read_text(encoding="utf-8")
        self.toml_path.write_text(text.replace('"100"', '"999"'), encoding="utf-8")
        rc, _, stderr = self._run(["verify"])
        self.assertEqual(rc, 1)
        self.assertIn("drifted", stderr)
        self.assertIn("p1.toml", stderr)
        # The error message must include the exact re-sign hint so the
        # next agent / reviewer doesn't have to guess.
        self.assertIn("python -m law.audit sign", stderr)

    def test_verify_fails_when_signed_file_is_deleted(self) -> None:
        self._run(["sign", str(self.toml_path)])
        self.toml_path.unlink()
        rc, _, stderr = self._run(["verify"])
        self.assertEqual(rc, 1)
        self.assertIn("file missing", stderr)

    def test_verify_strict_flags_unsigned_files(self) -> None:
        """Default ``verify`` rejects signable files that aren't registered."""
        # Sign neither file. Verify must fail.
        rc, _, stderr = self._run(["verify"])
        self.assertEqual(rc, 1)
        self.assertIn("not registered", stderr)

    def test_verify_allow_unsigned_tolerates_unsigned_files(self) -> None:
        """``--allow-unsigned`` lets verify pass with no registry entries.

        Used as a one-time bootstrap before the signing pass. Never the
        default — silent additions defeat the lock.
        """
        rc, _, _ = self._run(["verify", "--allow-unsigned"])
        self.assertEqual(rc, 0)

    def test_resign_after_drift_recovers(self) -> None:
        """sign → modify → verify-fails → re-sign → verify-passes."""
        # Sign both files so strict-verify has nothing else to complain
        # about; the drift-recovery semantics are what we're checking.
        self._run(["sign", str(self.py_path), str(self.toml_path)])
        text = self.py_path.read_text(encoding="utf-8")
        self.py_path.write_text(text.replace("X_VALUE = 100", "X_VALUE = 999"), encoding="utf-8")
        rc, _, _ = self._run(["verify"])
        self.assertEqual(rc, 1)
        self._run(["sign", str(self.py_path)])
        rc, _, _ = self._run(["verify"])
        self.assertEqual(rc, 0)

    def test_status_reports_counts(self) -> None:
        rc, stdout, _ = self._run(["status"])
        self.assertEqual(rc, 0)
        # Both files unsigned at this point.
        self.assertIn("unsigned:       2", stdout)
        self.assertIn("signed (clean): 0", stdout)
        self._run(["sign", str(self.py_path), str(self.toml_path)])
        rc, stdout, _ = self._run(["status"])
        self.assertEqual(rc, 0)
        self.assertIn("signed (clean): 2", stdout)
        self.assertIn("unsigned:       0", stdout)

    def test_sign_all_discovers_every_signable_file(self) -> None:
        rc, stdout, _ = self._run(["sign", "--all"])
        self.assertEqual(rc, 0)
        self.assertIn("2 file(s) signed", stdout)

    def test_sign_rejects_nonexistent_file(self) -> None:
        rc, _, stderr = self._run(["sign", str(self.repo_root / "law" / "missing.py")])
        self.assertEqual(rc, 2)
        self.assertIn("does not exist", stderr)

    def test_sign_rejects_init_py(self) -> None:
        init = self.repo_root / "law" / "testjuri" / "__init__.py"
        rc, _, stderr = self._run(["sign", str(init)])
        self.assertEqual(rc, 2)
        self.assertIn("not a signable", stderr)

    def test_sign_rejects_unrelated_path(self) -> None:
        # A file outside law/ — like the CLI module's host repo file —
        # is not signable.
        bad = self.repo_root / "Makefile"
        bad.write_text("", encoding="utf-8")
        rc, _, stderr = self._run(["sign", str(bad)])
        self.assertEqual(rc, 2)
        self.assertIn("not a signable", stderr)


class AuditRegistryFormatTest(unittest.TestCase):
    """The emitted registry is deterministic and parses cleanly."""

    def test_emitted_registry_is_sorted_and_parses(self) -> None:
        entries = {
            "law/b.py": {"hash": "sha256:bbb", "audited_by": "x", "audited_on": "2026-05-09"},
            "law/a.py": {"hash": "sha256:aaa", "audited_by": "x", "audited_on": "2026-05-09"},
        }
        text = audit._format_registry(entries)
        # law/a.py table header must appear before law/b.py.
        self.assertLess(text.find('["law/a.py"]'), text.find('["law/b.py"]'))
        # Round-trips via tomllib.
        parsed = tomllib.loads(text)
        self.assertEqual(set(parsed.keys()), {"law/a.py", "law/b.py"})
        self.assertEqual(parsed["law/a.py"]["hash"], "sha256:aaa")


class AuditDiscoveryExcludesHelpersTest(unittest.TestCase):
    """LOCK.md § 1: ``law/_utils/`` helpers are NOT locked.

    The discovery walk must skip them so ``--all`` / strict-verify don't
    sweep them in.
    """

    def test_discovery_excludes_law_utils_constants_and_money(self) -> None:
        # Use the real repo (read-only) — discovery against the live tree
        # must NOT include the helpers.
        signable = audit._discover_all_signable()
        rels = {audit._to_rel_path(p) for p in signable}
        self.assertNotIn("law/_utils/constants.py", rels)
        self.assertNotIn("law/_utils/money.py", rels)
        # And the CLI module itself is not in scope.
        self.assertNotIn("law/audit.py", rels)

    def test_discovery_excludes_test_files(self) -> None:
        # ``_test.py`` files are NOT in the A4 default scope (LOCK.md § 6
        # Q2 recommends locking them later; deferred per A4 brief).
        signable = audit._discover_all_signable()
        rels = {audit._to_rel_path(p) for p in signable}
        for rel in rels:
            self.assertFalse(
                rel.endswith("_test.py"),
                f"discovery unexpectedly included test file: {rel}",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
