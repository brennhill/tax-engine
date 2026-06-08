from __future__ import annotations

import csv
import json
import tempfile
import unittest
import io
from pathlib import Path
from contextlib import redirect_stdout

from tax_pipeline.analysis_inputs import missing_structured_inputs
from tax_pipeline.y2025.germany_inputs import load_joint_ordinary_inputs_2025
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.validate_workspace import main as validate_workspace_main
from tests.generated_demo import GeneratedDemoWorkspace, generate_demo_workspace

DEMO_ROOT = Path(__file__).resolve().parents[2] / "years" / "demo-2025"


class DemoWorkspaceRuntimeTest(unittest.TestCase):
    def test_demo_workspace_passes_validator_command(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = validate_workspace_main(["demo-2025"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("READY", output)
        self.assertIn("demo-2025", output)

    def test_materialize_demo_workspace_copies_demo_into_numeric_year_tree(self) -> None:
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            materialized = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)

            self.assertEqual(materialized.year, 2025)
            self.assertTrue(materialized.profile_path.exists())
            self.assertTrue((materialized.year_root / "README.md").exists())
            self.assertTrue(materialized.analysis_root.exists())
            self.assertTrue((materialized.tax_positions_root / "README.md").exists())

    def test_materialize_demo_workspace_replaces_existing_numeric_year_tree(self) -> None:
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            stale = first.year_root / "outputs" / "analysis-steps" / "stale.txt"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("stale")

            second = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)

            self.assertEqual(second.year_root, first.year_root)
            self.assertFalse(stale.exists())

    def test_materialize_demo_workspace_replaces_existing_nested_year_tree(self) -> None:
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            nested_output = first.year_root / "outputs" / "analysis-steps" / "old.txt"
            nested_raw = first.year_root / "raw" / "crypto" / "old.txt"
            nested_output.parent.mkdir(parents=True, exist_ok=True)
            nested_raw.parent.mkdir(parents=True, exist_ok=True)
            nested_output.write_text("stale")
            nested_raw.write_text("stale")

            second = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)

            self.assertEqual(second.year_root, first.year_root)
            self.assertFalse(nested_output.exists())
            self.assertFalse(nested_raw.exists())

    def test_materialized_demo_workspace_runs_with_treaty_dividend_invariant(self) -> None:
        from tax_pipeline.demo_workspace import materialize_demo_workspace
        from tax_pipeline.run_year import run_year

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)

            with redirect_stdout(io.StringIO()):
                run_year(root, "2025", workspace_root=paths.year_root)

            germany_results = json.loads((paths.analysis_root / "germany-model-results.json").read_text())
            us_results = json.loads((paths.analysis_root / "us-tax-estimate.json").read_text())

        self.assertEqual(germany_results["capital"]["treaty_us_source_dividend_gross_eur"], "280.00")
        self.assertEqual(us_results["treaty_resourcing"]["us_source_dividends_usd"], "316.03")


class DemoWorkspaceConfigTest(unittest.TestCase):
    def test_demo_config_is_single_person_cross_border(self) -> None:
        profile = json.loads((DEMO_ROOT / "config" / "profile.json").read_text())
        with (DEMO_ROOT / "config" / "people.csv").open(newline="") as handle:
            people = list(csv.DictReader(handle))

        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["person_id"], "person_1")
        self.assertEqual(people[0]["relationship_role"], "taxpayer")
        self.assertEqual(people[0]["citizenship"], "US,DE")
        self.assertEqual(profile["jurisdictions"]["germany"]["filing_posture"], "single")
        self.assertEqual(profile["jurisdictions"]["usa"]["filing_posture"], "single")

    def test_demo_config_includes_one_germany_prepayment_and_one_us_estimate(self) -> None:
        with (DEMO_ROOT / "config" / "payments.csv").open(newline="") as handle:
            payments = list(csv.DictReader(handle))
        with (DEMO_ROOT / "config" / "elections.csv").open(newline="") as handle:
            elections = list(csv.DictReader(handle))

        self.assertEqual(
            [(row["jurisdiction"], row["payment_type"]) for row in payments],
            [
                ("germany", "income_tax_prepayment"),
                ("usa", "estimated_tax_payment"),
            ],
        )
        self.assertIn(("germany", "filing_posture", "single"), [(r["jurisdiction"], r["key"], r["value"]) for r in elections])
        self.assertIn(("usa", "filing_posture", "single"), [(r["jurisdiction"], r["key"], r["value"]) for r in elections])
        self.assertIn(("usa", "use_treaty_resourcing", "true"), [(r["jurisdiction"], r["key"], r["value"]) for r in elections])


class DemoWorkspaceInputsTest(unittest.TestCase):
    def test_demo_workspace_has_all_required_structured_inputs(self) -> None:
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)

            self.assertEqual(missing_structured_inputs(paths), [])

    def test_demo_workspace_loaders_support_single_person_cross_border_case(self) -> None:
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)

            germany_inputs = load_joint_ordinary_inputs_2025(paths)
            usa_inputs = load_us_assessment_inputs_2025(paths)

            self.assertEqual(germany_inputs.filing_posture, "single")
            self.assertEqual(len(germany_inputs.people), 1)
            self.assertEqual(usa_inputs.profile.filing_status_label, "Single")
            self.assertEqual(usa_inputs.profile.spouse_name_for_mfs_line, "")


class DemoWorkspaceOutputsTest(unittest.TestCase):
    demo: GeneratedDemoWorkspace

    @classmethod
    def setUpClass(cls) -> None:
        cls.demo = generate_demo_workspace()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.demo.cleanup()

    def test_demo_workspace_includes_checked_in_normalized_helper_artifacts(self) -> None:
        self.assertEqual(json.loads((DEMO_ROOT / "normalized" / "documents.json").read_text()), [])
        self.assertTrue((DEMO_ROOT / "normalized" / "facts" / "REVIEW.md").exists())
        self.assertTrue((DEMO_ROOT / "normalized" / "facts" / "VALIDATION.md").exists())
        self.assertTrue((DEMO_ROOT / "normalized" / "facts" / "index.json").exists())
        self.assertTrue((DEMO_ROOT / "normalized" / "facts" / "validation.json").exists())

    def test_demo_outputs_are_single_person_and_cross_border(self) -> None:
        paths = self.demo.paths
        germany_summary = (paths.analysis_root / "germany-summary.md").read_text()
        germany_results = json.loads((paths.analysis_root / "germany-model-results.json").read_text())
        germany_trace = (paths.analysis_root / "germany-model-trace.csv").read_text()
        usa_summary = (paths.analysis_root / "us-tax-estimate.md").read_text()
        germany_index = (paths.germany_forms_root / "index.md").read_text()
        usa_index = (paths.usa_forms_root / "index.md").read_text()
        usa_entry = (paths.analysis_root / "us-treaty-entry-sheet.md").read_text()

        self.assertNotIn("person_2", germany_summary)
        self.assertFalse(
            any(key.startswith("person_2_bank_certificate_") for key in germany_results["refunds"]),
            germany_results["refunds"],
        )
        self.assertFalse(
            any("spouse_bank" in key for key in germany_results["refunds"]),
            germany_results["refunds"],
        )
        self.assertNotIn("person_2_bank_certificate_", germany_trace)
        self.assertNotIn("spouse_bank", germany_trace)
        self.assertIn("vanilla checkpoint", germany_summary.lower())
        self.assertNotIn("partner bank", germany_summary.lower())
        self.assertNotIn("dher", germany_summary.lower())
        self.assertIn("single", germany_index.lower())
        self.assertIn("single", usa_summary.lower())
        self.assertIn("refund", usa_summary.lower())
        self.assertNotIn("married filing separately", usa_summary.lower())
        self.assertNotIn("2,000 usd", usa_summary.lower())
        self.assertIn("single", usa_index.lower())
        self.assertIn("treaty", usa_entry.lower())
        self.assertNotIn("nonresident alien spouse", usa_entry.lower())
        self.assertNotIn("nonresident alien spouse", usa_summary.lower())


if __name__ == "__main__":
    unittest.main()
