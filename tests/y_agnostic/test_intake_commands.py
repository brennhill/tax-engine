from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tax_pipeline.intake.commands import get_readiness, run_pipeline
from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class IntakeCommandsTest(unittest.TestCase):
    def test_get_readiness_returns_structured_validation_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)
            paths.profile_path.unlink()

            payload = get_readiness(PROJECT_ROOT, "2026", workspace_root=workspace_root)

            self.assertFalse(payload["ready"])
            self.assertIn("config/profile.json", payload["groups"]["missing_config"])
            self.assertIn("normalized/reference-data/de-tax-constants.csv", payload["groups"]["missing_structured"])
            self.assertTrue(any(line.startswith("NOT READY") for line in payload["ready_lines"]))

    def test_readiness_route_exposes_machine_readable_and_human_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/readiness?year=2026&workspace={workspace_root}",
            )

            self.assertEqual(status, 200)
            self.assertFalse(payload["ready"])
            self.assertIn("groups", payload)
            self.assertIn("sections", payload)
            self.assertIn("ready_lines", payload)
            self.assertTrue(any("Fix the items above" in line for line in payload["ready_lines"]))

    @mock.patch("tax_pipeline.intake.commands.run_year")
    def test_run_pipeline_returns_status_and_output_pointers(self, run_year_mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            payload = run_pipeline(PROJECT_ROOT, "2026", workspace_root=workspace_root)

            run_year_mock.assert_called_once_with(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["outputs"]["locations"]["facts_review"], "normalized/facts/REVIEW.md")
            self.assertEqual(payload["outputs"]["locations"]["analysis"], "outputs/analysis-steps/")
            self.assertEqual(payload["outputs"]["locations"]["forms"], "outputs/forms/")
            self.assertNotIn(str(workspace_root), str(payload["outputs"]))

    @mock.patch("tax_pipeline.intake.commands.run_year")
    def test_run_route_exposes_status_separately_from_readiness(self, run_year_mock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/run",
                body={"year": "2026", "workspace": str(workspace_root)},
            )

            self.assertEqual(status, 202)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["outputs"]["locations"]["analysis"], "outputs/analysis-steps/")
            self.assertNotIn(str(workspace_root), str(payload["outputs"]))
            run_year_mock.assert_called_once_with(PROJECT_ROOT, "2026", workspace_root=workspace_root)


if __name__ == "__main__":
    unittest.main()
