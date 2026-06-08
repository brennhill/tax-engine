"""H3 tests for boolean-typo detection in ``tax-pipeline-validate``.

Background: the wizard (``tax-pipeline-intake``) is now the canonical
input surface for the workspace's CSV / JSON config. The CSVs are an
export / audit format — hand-editing them is supported but no longer
the recommended workflow. A typo in a boolean column ("ture" instead of
"true", "Yes" instead of "true") used to slip through validation
because downstream coercion in the rule loaders is permissive in
places. H3 surfaces those typos at the validation step so the user
knows what to fix before the pipeline runs.
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.validate_workspace import build_validation_report
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _scaffold(workspace_root: Path):
    paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
    ensure_year_scaffold(paths)
    return paths


def _rewrite_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


class PeopleBooleanTypoTest(unittest.TestCase):
    def test_clean_workspace_has_no_invalid_boolean_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(invalid, [])

    def test_typo_in_us_filer_column_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            rows = _read_csv(paths.people_path)
            rows[0]["us_filer"] = "ture"
            _rewrite_csv(paths.people_path, rows)

            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(len(invalid), 1, msg=str(report.errors))
            self.assertIn("us_filer", invalid[0])
            # The error is surfaced with a plain-language hint pointing
            # at the wizard so the user knows the canonical edit
            # surface, not just that the value is wrong.
            config_section = dict(report.sections).get("Config", [])
            self.assertTrue(
                any(
                    "tax-pipeline-intake" in line
                    and "true" in line
                    and "false" in line
                    for line in config_section
                ),
                msg=f"expected hint pointing at the wizard, got {config_section!r}",
            )

    def test_yes_no_values_are_flagged(self) -> None:
        # The previous CSV contract used permissive coercion that would
        # accept "yes"/"no". Now we only accept the canonical
        # ``true``/``false`` so the wizard's writer and the validator
        # agree on a single grammar.
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            rows = _read_csv(paths.people_path)
            rows[0]["nra_for_us_return"] = "yes"
            _rewrite_csv(paths.people_path, rows)

            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(len(invalid), 1)
            self.assertIn("nra_for_us_return", invalid[0])

    def test_capitalized_true_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            rows = _read_csv(paths.people_path)
            rows[0]["is_taxpayer"] = "True"
            _rewrite_csv(paths.people_path, rows)

            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(len(invalid), 1)
            self.assertIn("is_taxpayer", invalid[0])

    def test_empty_value_in_boolean_column_is_tolerated(self) -> None:
        # An empty cell means "column not provided"; downstream code
        # already handles this, so we should not flood the validator
        # with spurious errors for legitimately-omitted optional fields.
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            rows = _read_csv(paths.people_path)
            rows[0]["nra_for_us_return"] = ""
            _rewrite_csv(paths.people_path, rows)

            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(invalid, [])


class ElectionsBooleanTypoTest(unittest.TestCase):
    def test_typo_in_enabled_election_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            rows = _read_csv(paths.elections_path)
            for row in rows:
                if row.get("key") == "enabled" and row.get("jurisdiction") == "germany":
                    row["value"] = "ture"
                    break
            _rewrite_csv(paths.elections_path, rows)

            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(len(invalid), 1)
            self.assertIn("enabled", invalid[0])

    def test_non_boolean_election_keys_are_unaffected(self) -> None:
        # ``filing_posture`` is a free-text election (single, joint,
        # mfs_nra_spouse, ...). The boolean validator must not produce
        # a false positive on those rows.
        with tempfile.TemporaryDirectory() as tmp:
            paths = _scaffold(Path(tmp) / "2026")
            report = build_validation_report(paths)
            invalid = [e for e in report.errors if e.startswith("invalid_boolean:")]
            self.assertEqual(invalid, [])


if __name__ == "__main__":
    unittest.main()
