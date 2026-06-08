"""Regression test: prevent the legal-audit-vs-audit-note naming drift.

Two unrelated artifacts share the word "audit":

  1. The audit packet directory at ``outputs/legal-audit/<country>/`` —
     written by ``tax_pipeline/legal_audit/{germany,usa}.py``.
  2. The audit note at ``outputs/analysis-steps/<country>-audit-note.md``
     — written by ``tax_pipeline/pipelines/y2025/{germany,us}_model.py``.

Until 2026-05-04 both were called "legal-audit", which made it impossible
to know which artifact a filename referred to. The audit-note files were
renamed to ``<country>-audit-note.md`` to disambiguate. This test guards
the rename across all workspaces under ``years/``.

Authority context: this is a repo-internal naming-hygiene rule, not a
tax-law citation. It exists to keep the audit-trail vocabulary clean.
"""
from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
YEARS_ROOT = PROJECT_ROOT / "years"


class AuditNoteNamingTest(unittest.TestCase):
    """Reject any ``*legal-audit*.md`` filename under ``analysis-steps/``.

    The ``outputs/legal-audit/`` directory itself is NOT in scope — that
    directory is the correctly-named audit-packet artifact. We only audit
    the ``analysis-steps`` siblings here.
    """

    def test_no_analysis_step_filename_uses_legal_audit(self) -> None:
        if not YEARS_ROOT.is_dir():
            self.skipTest("no years/ workspaces present")

        offenders: list[Path] = []
        for workspace in sorted(YEARS_ROOT.iterdir()):
            analysis_root = workspace / "outputs" / "analysis-steps"
            if not analysis_root.is_dir():
                continue
            for entry in sorted(analysis_root.iterdir()):
                if entry.is_file() and "legal-audit" in entry.name:
                    offenders.append(entry)

        self.assertEqual(
            offenders,
            [],
            "Found analysis-steps files using the legacy 'legal-audit' name. "
            "These should be 'audit-note' files instead — the 'legal-audit' "
            "name belongs to the outputs/legal-audit/ directory artifact: "
            f"{[str(p) for p in offenders]}",
        )


if __name__ == "__main__":
    unittest.main()
