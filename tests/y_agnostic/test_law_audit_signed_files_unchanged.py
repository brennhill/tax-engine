"""Invariant: every signed law-shadow file matches its registered hash.

Per proposal A4 of ``.review/2026-05-08-platform-flexibility-review.md``
and ``LOCK.md`` § 2 Layer 1, the law-shadow tree (29 sibling TOML data
files + 52 shadow ``.py`` files under ``law/``) is locked at the
file-content level. ``.audit/hashes.toml`` records the SHA-256 digest of
every signed file at the moment of audit; this invariant test re-hashes
every entry and fails if any digest has drifted.

This is the structural CI check that turns "did the AI agent silently
change a vetted constant?" from "answerable only via ``git log -p``"
into "fails ``make check-invariants`` immediately."

Complementary protection layers:

* ``tests/test_law_data_files_round_trip.py`` (F1) — value-level: every
  TOML constant has the three required fields (``value``, ``authority``,
  ``citation_url``) and ``Decimal(value)`` round-trips.
* This test (A4) — file-level: every byte of a signed file matches the
  registered hash. Catches edits that round-trip cleanly through F1's
  value-level checks (e.g. citation_url tampering, authority text edits,
  comment-level rewrites that don't change the numeric value).

To re-sign after an intentional update::

    python -m law.audit sign <path>

Helpers under ``law/_utils/`` and test files (``*_test.py``) are out of
A4 scope by design (LOCK.md § 1 / § 6 Q2; see ``law/audit.py`` docstring).
"""
from __future__ import annotations

import unittest

from law import audit


class LawAuditSignedFilesUnchangedTest(unittest.TestCase):
    """Re-hash every entry in ``.audit/hashes.toml`` and assert no drift."""

    def test_no_signed_file_has_drifted(self) -> None:
        entries = audit._load_registry()
        if not entries:
            self.fail(
                "No entries in .audit/hashes.toml — the signing pass "
                "(A4) must have run before this invariant takes effect. "
                "Sign all law-shadow files with: "
                "python -m law.audit sign --all"
            )
        _, _, drifted = audit._classify(entries)
        if drifted:
            lines = ["The following signed law-shadow files have drifted:"]
            for rel, registered, current in drifted:
                lines.append(f"  {rel}")
                lines.append(f"    registered: {registered}")
                lines.append(f"    current:    {current}")
                lines.append(
                    f"    re-sign with: python -m law.audit sign {rel}"
                )
            self.fail("\n".join(lines))

    def test_no_signable_file_is_unsigned(self) -> None:
        """Every signable file under ``law/`` must be in the registry.

        Otherwise an agent could quietly add a new shadow file (with a
        new constant or amended legal text) that bypasses the lock until
        someone manually runs ``sign``. Failing closed forces the new
        file to be signed before it can land.
        """
        entries = audit._load_registry()
        _, unsigned, _ = audit._classify(entries)
        if unsigned:
            rels = [audit._to_rel_path(p) for p in unsigned]
            self.fail(
                "The following signable files under law/ are not in "
                ".audit/hashes.toml:\n  "
                + "\n  ".join(rels)
                + "\n\nSign with: python -m law.audit sign --all"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
