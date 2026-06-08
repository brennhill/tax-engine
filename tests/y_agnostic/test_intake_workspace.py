from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths

from tax_pipeline.intake.workspace import (
    create_workspace,
    open_workspace,
    resolve_workspace_paths,
    write_intake_basics,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return [{key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)]


class IntakeWorkspaceTest(unittest.TestCase):
    def test_resolve_workspace_paths_defaults_to_home_taxes_year(self) -> None:
        paths = resolve_workspace_paths(PROJECT_ROOT, "2026")

        self.assertEqual(paths.workspace_root, (Path.home() / "taxes" / "2026").resolve())
        self.assertEqual(paths.year, 2026)

    def test_open_workspace_returns_metadata_without_rewriting_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            sentinel = paths.workspace_root / "notes.txt"
            sentinel.write_text("keep me")
            original_mtime = sentinel.stat().st_mtime_ns

            metadata = open_workspace(PROJECT_ROOT, "2026", workspace_root=workspace_root)

            self.assertEqual(metadata["workspace_root"], str(workspace_root.resolve()))
            self.assertEqual(metadata["year"], 2026)
            self.assertEqual(metadata["people_count"], 1)
            self.assertEqual(metadata["germany_filing_posture"], "single")
            self.assertEqual(metadata["usa_filing_posture"], "single")
            self.assertEqual(sentinel.read_text(), "keep me")
            self.assertEqual(sentinel.stat().st_mtime_ns, original_mtime)

    def test_write_intake_basics_updates_csvs_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_workspace_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            create_workspace(PROJECT_ROOT, "2026", workspace_root=workspace_root)

            payload = {
                "household": {
                    "marital_status_on_dec_31": "married",
                    "germany_filing_posture": "married_joint",
                    "usa_filing_posture": "mfs_nra_spouse",
                },
                "people": [
                    {
                        "person_id": "person_1",
                        "display_name": "Alex Example",
                        "first_name": "Alex",
                        "last_name": "Example",
                        "relationship_role": "taxpayer",
                        "elster_order": "1",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "citizenship": "US",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": False,
                    },
                    {
                        "person_id": "person_2",
                        "display_name": "Sam Example",
                        "first_name": "Sam",
                        "last_name": "Example",
                        "relationship_role": "spouse",
                        "elster_order": "2",
                        "us_filer": False,
                        "is_taxpayer": False,
                        "is_spouse": True,
                        "citizenship": "DE",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": True,
                    },
                ],
                "payments": [
                    {
                        "jurisdiction": "germany",
                        "person_id": "",
                        "payment_type": "income_tax_prepayment",
                        "amount": "500.00",
                        "currency": "EUR",
                        "source": "manual",
                        "note": "Quarterly prepayment",
                    },
                    {
                        "jurisdiction": "usa",
                        "person_id": "person_1",
                        "payment_type": "estimated_tax_payment",
                        "amount": "250.00",
                        "currency": "USD",
                        "source": "manual",
                        "note": "IRS estimate",
                    },
                ],
                "jurisdictions": {
                    "germany": {"enabled": True},
                    "usa": {
                        "enabled": True,
                        "us_ftc_method": "paid",
                        "use_treaty_resourcing": True,
                        "elect_joint_return_with_nra_spouse": False,
                    },
                },
            }

            metadata = write_intake_basics(paths, payload)

            self.assertEqual(metadata["people_count"], 2)
            self.assertEqual(metadata["germany_filing_posture"], "married_joint")
            self.assertEqual(metadata["usa_filing_posture"], "mfs_nra_spouse")

            people_rows = _read_csv_rows(paths.people_path)
            self.assertEqual(len(people_rows), 2)
            self.assertEqual(people_rows[0]["display_name"], "Alex Example")
            self.assertEqual(people_rows[1]["display_name"], "Sam Example")
            self.assertEqual(people_rows[1]["nra_for_us_return"], "true")

            payments_rows = _read_csv_rows(paths.payments_path)
            self.assertEqual(len(payments_rows), 2)
            self.assertEqual(payments_rows[0]["payment_type"], "income_tax_prepayment")
            self.assertEqual(payments_rows[1]["payment_type"], "estimated_tax_payment")

            elections_rows = _read_csv_rows(paths.elections_path)
            by_pair = {
                (row["jurisdiction"], row["key"]): row["value"]
                for row in elections_rows
            }
            self.assertEqual(by_pair[("household", "marital_status_on_dec_31")], "married")
            self.assertEqual(by_pair[("germany", "filing_posture")], "joint")
            self.assertEqual(by_pair[("usa", "filing_posture")], "mfs")
            self.assertEqual(by_pair[("usa", "us_ftc_method")], "paid")
            self.assertEqual(by_pair[("usa", "use_treaty_resourcing")], "true")

            profile = json.loads(paths.profile_path.read_text())
            self.assertEqual(profile["taxpayer"]["name"], "Alex Example")
            self.assertEqual(profile["spouse"]["name"], "Sam Example")
            self.assertEqual(profile["household"]["marital_status_on_dec_31"], "married")
            self.assertEqual(profile["household"]["germany_filing_status"], "joint")
            self.assertEqual(profile["household"]["us_filing_status"], "mfs")
            self.assertEqual(profile["jurisdictions"]["germany"]["filing_posture"], "married_joint")
            self.assertEqual(profile["jurisdictions"]["usa"]["filing_posture"], "mfs_nra_spouse")
            self.assertTrue(profile["elections"]["use_treaty_resourcing"])
            self.assertEqual(
                [slot["display_name"] for slot in profile["german_return"]["person_slots"]],
                ["Alex Example", "Sam Example"],
            )

    def test_write_intake_basics_rejects_unsupported_household_posture_combinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_workspace_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            create_workspace(PROJECT_ROOT, "2026", workspace_root=workspace_root)

            payload = {
                "household": {
                    "marital_status_on_dec_31": "single",
                    "germany_filing_posture": "married_joint",
                    "usa_filing_posture": "single",
                },
                "people": [
                    {
                        "person_id": "person_1",
                        "display_name": "Alex Example",
                        "relationship_role": "taxpayer",
                        "elster_order": "1",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "citizenship": "US",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": False,
                    }
                ],
                "payments": [],
                "jurisdictions": {
                    "germany": {"enabled": True},
                    "usa": {"enabled": True},
                },
            }

            with self.assertRaisesRegex(ValueError, "single household"):
                write_intake_basics(paths, payload)

    def test_write_intake_basics_rejects_germany_married_separate_until_26a_surface_exists(self) -> None:
        # § 26a EStG assigns income and deductions by spouse for separate assessment.
        # The public intake must fail closed until the full Germany output pipeline supports that surface.
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_workspace_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            create_workspace(PROJECT_ROOT, "2026", workspace_root=workspace_root)

            payload = {
                "household": {
                    "marital_status_on_dec_31": "married",
                    "germany_filing_posture": "married_separate",
                    "usa_filing_posture": "mfs_nra_spouse",
                },
                "people": [
                    {
                        "person_id": "person_1",
                        "display_name": "Alex Example",
                        "relationship_role": "taxpayer",
                        "elster_order": "1",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "citizenship": "US",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": False,
                    },
                    {
                        "person_id": "person_2",
                        "display_name": "Sam Example",
                        "relationship_role": "spouse",
                        "elster_order": "2",
                        "us_filer": False,
                        "is_taxpayer": False,
                        "is_spouse": True,
                        "citizenship": "DE",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": True,
                    },
                ],
                "payments": [],
                "jurisdictions": {
                    "germany": {"enabled": True},
                    "usa": {"enabled": True},
                },
            }

            with self.assertRaisesRegex(ValueError, "married_separate.*not supported"):
                write_intake_basics(paths, payload)


if __name__ == "__main__":
    unittest.main()
