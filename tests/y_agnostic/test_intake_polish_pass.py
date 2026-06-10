"""Regression tests for the polish-pass UI + API surface.

Locks the five onboarding/usability improvements landed together:

  1. Stepped wizard nav (vertical stepper, per-section status badges,
     first-run quick-start cards).
  2. Live readiness right-rail with deep-link error items.
  3. Drag-and-drop batch uploader with classifier preview (single
     ``/api/uploads/classify-batch`` endpoint).
  4. Structured run-progress board (icons + stage failure rows).
  5. In-app output preview for high-value files (``/api/output-preview``
     + ``preview_eligible`` flag on the manifest).

Authority: UI/UX contract only; legal-numeric correctness is covered
by other y_agnostic / y2025 tests.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.intake.server import dispatch_request, dispatch_response
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "tax_pipeline" / "intake" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
APP_JS = STATIC_DIR / "app.js"


class StepperUITest(unittest.TestCase):
    """Vertical stepper nav + per-section status badges + first-run cards."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")

    def test_html_contains_vertical_stepper_with_13_steps(self) -> None:
        # The flat <nav class="wizard-nav"> button row was replaced with
        # a vertical stepper. The Readiness screen folded into the rail,
        # so the stepper carries 13 actionable steps (was 14 with the
        # old Readiness button).
        self.assertIn('class="wizard-stepper"', self.html)
        self.assertIn('id="stepper-list"', self.html)
        self.assertEqual(self.html.count('class="stepper-step'), 13)
        for target in (
            "workspace", "household", "identity", "bank_accounts",
            "payments", "postures", "de_deductions", "vorabpauschale",
            "carryovers", "children", "documents", "run", "outputs",
        ):
            with self.subTest(target=target):
                self.assertIn(
                    f'data-nav-target="{target}"',
                    self.html,
                    f"Stepper missing step for {target}",
                )

    def test_first_run_quick_start_cards_are_present(self) -> None:
        # The Workspace screen leads with three quick-start cards before
        # the legacy year/path form. Cards drive the demo / new-year /
        # roll-forward flows respectively.
        self.assertIn('id="quick-start-cards"', self.html)
        self.assertIn('data-quick-start="demo"', self.html)
        self.assertIn('data-quick-start="new"', self.html)
        self.assertIn('data-quick-start="roll-forward"', self.html)

    def test_stepper_js_provides_status_helpers(self) -> None:
        self.assertIn("function setStepStatus", self.js)
        self.assertIn("function setStepperCurrent", self.js)
        self.assertIn("function setStepperLocked", self.js)
        self.assertIn("function refreshStepperStatuses", self.js)

    def test_quick_start_handlers_wire_demo_and_roll_forward(self) -> None:
        self.assertIn("/api/workspace/demo", self.js)
        self.assertIn("/api/workspace/roll-forward", self.js)
        self.assertIn("function handleQuickStart", self.js)


class WorkspaceEndpointsTest(unittest.TestCase):
    """``/api/workspace/demo`` materializes the demo; ``/roll-forward`` copies config."""

    def test_demo_endpoint_materializes_demo_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/workspace/demo",
                body={"year": "2025", "workspace": str(workspace_root)},
            )
            self.assertEqual(status, 201, payload)
            self.assertIn("year", payload)
            # The materialized demo carries the synthetic config trio.
            self.assertTrue((workspace_root / "config" / "profile.json").exists())
            self.assertTrue((workspace_root / "config" / "people.csv").exists())
            self.assertTrue((workspace_root / "config" / "payments.csv").exists())

    def test_roll_forward_requires_both_years_and_copies_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "2025"
            target = Path(tmp) / "2026"
            # First materialize 2025 as the source.
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/workspace/demo",
                body={"year": "2025", "workspace": str(source)},
            )
            self.assertEqual(status, 201, payload)
            # Missing source_year should error.
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/workspace/roll-forward",
                body={"year": "2026", "workspace": str(target)},
            )
            self.assertEqual(status, 400)
            self.assertIn("source_year", payload["error"])
            # With both years, config is copied over.
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/workspace/roll-forward",
                body={
                    "source_year": "2025",
                    "year": "2026",
                    "workspace": str(target),
                },
            )
            self.assertEqual(status, 201, payload)
            self.assertTrue((target / "config" / "profile.json").exists())
            self.assertTrue((target / "config" / "people.csv").exists())


class ReadinessRailTest(unittest.TestCase):
    """Live readiness side-panel — aside + URL + render helper."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")

    def test_html_contains_readiness_rail_aside(self) -> None:
        self.assertIn('id="readiness-rail"', self.html)
        self.assertIn('id="readiness-badge"', self.html)
        self.assertIn('id="readiness-rail-body"', self.html)
        # Raw report still available, but tucked behind a <details>.
        self.assertIn("<details", self.html)
        self.assertIn('id="readiness-output"', self.html)

    def test_js_provides_live_readiness_renderer(self) -> None:
        self.assertIn("async function refreshReadiness", self.js)
        self.assertIn("function renderReadinessRail", self.js)
        self.assertIn("/api/readiness", self.js)
        # Each save path triggers a re-poll.
        self.assertIn("refreshReadiness()", self.js)


class DragDropUploaderTest(unittest.TestCase):
    """Drag-and-drop batch upload + classify-batch endpoint."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")

    def test_html_contains_dropzone_and_batch_actions(self) -> None:
        self.assertIn('id="upload-dropzone"', self.html)
        self.assertIn('multiple', self.html)
        self.assertIn('id="upload-batch"', self.html)
        self.assertIn('id="upload-commit-all"', self.html)
        self.assertIn('id="upload-clear-all"', self.html)

    def test_js_wires_drop_events_and_classify_batch(self) -> None:
        self.assertIn('"drop"', self.js)
        self.assertIn('"dragover"', self.js)
        self.assertIn('/api/uploads/classify-batch', self.js)
        self.assertIn('function handleUploadFiles', self.js)
        self.assertIn('function commitUploadBatch', self.js)

    def test_classify_batch_endpoint_returns_predictions(self) -> None:
        status, payload = dispatch_request(
            PROJECT_ROOT,
            "POST",
            "/api/uploads/classify-batch",
            body={
                "filenames": [
                    "brokers/2024 1099 Composite.pdf",
                    "germany/Certificate of wage tax deduction 2025 12 December.pdf",
                    "totally_random.zip",
                ],
            },
        )
        self.assertEqual(status, 200, payload)
        predictions = payload["predictions"]
        self.assertEqual(len(predictions), 3)
        # First file should classify as a Schwab 1099 composite PDF.
        self.assertEqual(predictions[0]["doc_type"], "schwab_1099_pdf")
        self.assertEqual(predictions[0]["confidence"], "high")
        # Second should be a German Lohnsteuerbescheinigung.
        self.assertEqual(predictions[1]["bucket"], "germany")
        # Unrecognized → unknown + low confidence.
        self.assertEqual(predictions[2]["doc_type"], "unknown")
        self.assertEqual(predictions[2]["confidence"], "low")

    def test_classify_batch_rejects_missing_filenames(self) -> None:
        status, payload = dispatch_request(
            PROJECT_ROOT,
            "POST",
            "/api/uploads/classify-batch",
            body={},
        )
        self.assertEqual(status, 400)
        self.assertIn("filenames", payload["error"])


class RunProgressUITest(unittest.TestCase):
    """Structured run-progress board (stages + icons + failure rows)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")

    def test_html_uses_structured_run_board_not_pre(self) -> None:
        # ``<pre id="run-output">`` was replaced with ``<div>`` + the new
        # ``run-stage-board`` class so per-stage rows can carry icons /
        # failure expansions without <pre>'s monospace constraint.
        self.assertNotIn('<pre id="run-output"', self.html)
        self.assertIn('id="run-output"', self.html)
        self.assertIn('class="run-stage-board"', self.html)
        self.assertIn('id="run-summary"', self.html)

    def test_js_renders_stage_rows_with_state_classes(self) -> None:
        self.assertIn('run-stage-row is-', self.js)
        self.assertIn('run-stage-icon', self.js)
        self.assertIn('run-stage-failure', self.js)


class OutputPreviewTest(unittest.TestCase):
    """In-app output preview — eligibility flag, endpoint, modal markup."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")

    def test_html_contains_output_preview_modal(self) -> None:
        self.assertIn('id="output-preview-modal"', self.html)
        self.assertIn('id="output-preview-body"', self.html)
        self.assertIn('id="output-preview-close"', self.html)

    def test_js_wires_preview_button_and_modal(self) -> None:
        self.assertIn('async function openOutputPreview', self.js)
        self.assertIn('function renderOutputPreview', self.js)
        self.assertIn('/api/output-preview', self.js)
        self.assertIn('preview_eligible', self.js)

    def test_outputs_manifest_flags_high_value_files_as_preview_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            paths = resolve_year_paths(PROJECT_ROOT, "2025", workspace_root=workspace_root)
            paths.ensure_directories()
            (paths.analysis_root / "final-legal-output.json").write_text(
                json.dumps(
                    {
                        "germany": {
                            "refunds": {
                                "final_target_refund_eur": "1234.56",
                                "total_income_tax_eur": "9876.54",
                            },
                        },
                        "usa": {
                            "payments": {
                                "refund_without_treaty_resourcing_usd": "0.00",
                                "refund_with_treaty_resourcing_usd": "500.00",
                            },
                            "tax": {
                                "total_tax_with_treaty_resourcing_usd": "12000.00",
                            },
                        },
                        "_provenance": {
                            "rule_outputs": {
                                "germany": {"rule_a": {"fp": "abc"}},
                                "usa": {"rule_b": {"fp": "def"}},
                            },
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (paths.analysis_root / "DE-en-narrative.md").write_text("# Germany narrative", encoding="utf-8")
            # Forms file should NOT be preview-eligible.
            (paths.germany_forms_root / "index.md").write_text("# Germany forms", encoding="utf-8")

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/outputs?year=2025&workspace={workspace_root}",
            )
            self.assertEqual(status, 200)
            by_path = {item["relative_path"]: item for item in payload["files"]}

            self.assertTrue(
                by_path["outputs/analysis-steps/final-legal-output.json"]["preview_eligible"],
                "final-legal-output.json must be preview-eligible.",
            )
            self.assertTrue(
                by_path["outputs/analysis-steps/DE-en-narrative.md"]["preview_eligible"],
                "DE narrative must be preview-eligible.",
            )
            self.assertFalse(
                by_path["outputs/forms/germany/index.md"]["preview_eligible"],
                "Forms index.md should not surface a Preview button.",
            )

    def test_preview_endpoint_extracts_json_highlights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            paths = resolve_year_paths(PROJECT_ROOT, "2025", workspace_root=workspace_root)
            paths.ensure_directories()
            (paths.analysis_root / "final-legal-output.json").write_text(
                json.dumps(
                    {
                        "germany": {"refunds": {"final_target_refund_eur": "250.00"}},
                        "usa": {"payments": {"refund_with_treaty_resourcing_usd": "1200.00"}},
                        "_provenance": {"rule_outputs": {"germany": {"r": "f"}}},
                    }
                ),
                encoding="utf-8",
            )
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/output-preview?year=2025&workspace={workspace_root}&path=outputs/analysis-steps/final-legal-output.json",
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["kind"], "json")
            highlights = {h["label"]: h["amount"] for h in payload["highlights"]}
            self.assertIn("Germany — final refund / due", highlights)
            self.assertIn("U.S. — refund with treaty re-sourcing", highlights)
            self.assertEqual(payload["provenance_count"], 1)

    def test_preview_endpoint_serves_markdown_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            paths = resolve_year_paths(PROJECT_ROOT, "2025", workspace_root=workspace_root)
            paths.ensure_directories()
            (paths.analysis_root / "DE-en-narrative.md").write_text(
                "# Germany narrative\n\nLine one.\n",
                encoding="utf-8",
            )
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/output-preview?year=2025&workspace={workspace_root}&path=outputs/analysis-steps/DE-en-narrative.md",
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["kind"], "markdown")
            self.assertIn("Germany narrative", payload["body_text"])

    def test_preview_endpoint_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            paths = resolve_year_paths(PROJECT_ROOT, "2025", workspace_root=workspace_root)
            paths.ensure_directories()
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/output-preview?year=2025&workspace={workspace_root}&path=../../etc/passwd",
            )
            self.assertIn(status, (400, 403, 404))


if __name__ == "__main__":
    unittest.main()
