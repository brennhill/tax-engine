"""End-to-end tests for the ``elections.us_filing_required=false`` opt-out.

CLAUDE.md tax-rule requirements: the user-facing posture
``elections.us_filing_required`` is the canonical opt-out for the U.S.
pathway. When set to false, the engine must skip every US25-* /
TREATY25-* / BRIDGE25-* stage and every Form 1040 / 1116 / 2555 /
6251 / 8959 / Schedule B / D / SE renderer, while running the
Germany pipeline cleanly to completion.

Authority:

- 26 U.S.C. § 6012 — Persons required to make returns of income.
  https://www.law.cornell.edu/uscode/text/26/6012
- DBA-USA 1989 Art. 23 — Treaty re-sourcing has no U.S. side to feed
  when the U.S. pathway is disabled.
  https://www.irs.gov/pub/irs-trty/germany.pdf
- § 32d Abs. 5 EStG — German per-Posten foreign-tax credit continues
  to apply inside the German capital rule graph regardless of whether
  the U.S. side runs.
  https://www.gesetze-im-internet.de/estg/__32d.html

Structural invariant I13 (this commit): when a jurisdiction is
disabled, the corresponding artifacts must be explicitly absent (no
``us-tax-package.json``, no Form 1040, no Form 1116, etc.) rather than
silently emitting zero-valued forms. The final-legal-output carries a
top-level ``us_filing_required`` marker plus a citation-bearing
``reason`` on each ``not_applicable`` block.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tax_pipeline.y2025.cross_jurisdiction import (
    read_us_filing_required,
    should_include_bridge_2025_stages,
    should_include_treaty_2025_stages,
    should_include_us_2025_stages,
)
from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.intake.postures import POSTURE_REGISTRY
from tax_pipeline.run_year import run_year


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_de_only_demo() -> tuple[Path, str]:
    """Materialize the DE-only demo workspace, run the full pipeline,
    and return (year_root, captured_stdout)."""
    tempdir = tempfile.mkdtemp(prefix="de_only_demo_")
    root = Path(tempdir)
    paths = materialize_demo_workspace(root, demo_name="de-only-demo-2025", year=2025)
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_year(root, "2025", workspace_root=paths.year_root)
    return paths.year_root, buf.getvalue()


class UsFilingNotRequiredEndToEndTest(unittest.TestCase):
    """End-to-end run of the de-only-demo-2025 workspace.

    Asserts the DE pipeline completes, the U.S. side is explicitly
    absent (no rendered forms, no us-tax-package.json), and the
    final-legal-output records the opt-out posture.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.year_root, cls.stdout = _run_de_only_demo()

    def test_de_pipeline_produces_full_output(self) -> None:
        # § 36 Abs. 2 EStG final refund: the DE rule graph must run
        # end-to-end even though the U.S. side is disabled.
        analysis_root = self.year_root / "outputs" / "analysis-steps"
        results_path = analysis_root / "germany-model-results.json"
        self.assertTrue(results_path.exists(), "Germany model results must be written")
        results = json.loads(results_path.read_text(encoding="utf-8"))
        self.assertIn("refunds", results)
        self.assertIn("final_target_refund_eur", results["refunds"])

    def test_no_us_artifacts_are_written(self) -> None:
        # Structural invariant I13: U.S. artifacts must be explicitly
        # absent when us_filing_required=false. No US analysis-steps
        # JSON, no rendered Forms, no legal-audit output.
        analysis_root = self.year_root / "outputs" / "analysis-steps"
        for forbidden in (
            "us-tax-estimate.json",
            "us-tax-estimate.md",
            "us-treaty-package.json",
            "us-capital-results.json",
            "us-tax-trace.csv",
            "us-form-8949-income-buckets.csv",
            "us-audit-note.md",
            "us-supporting-statements.md",
            "us-treaty-entry-sheet.md",
        ):
            self.assertFalse(
                (analysis_root / forbidden).exists(),
                f"{forbidden} must not be produced when us_filing_required=false",
            )
        usa_forms_root = self.year_root / "outputs" / "forms" / "usa"
        if usa_forms_root.exists():
            self.assertEqual(
                list(usa_forms_root.glob("*.md")),
                [],
                "U.S. forms directory must be empty when us_filing_required=false",
            )

    def test_final_legal_output_marks_opt_out(self) -> None:
        analysis_root = self.year_root / "outputs" / "analysis-steps"
        final_path = analysis_root / "final-legal-output.json"
        self.assertTrue(final_path.exists())
        data = json.loads(final_path.read_text(encoding="utf-8"))
        # 26 U.S.C. § 6012 marker on the audit packet.
        self.assertIn("us_filing_required", data)
        self.assertIs(data["us_filing_required"], False)
        # The U.S. block uses the citation-bearing not_applicable reason.
        self.assertEqual(data["usa"]["forms"]["status"], "not_applicable")
        self.assertEqual(data["usa"]["legal_audit"]["status"], "not_applicable")
        self.assertIn(
            "26 U.S.C. § 6012",
            data["usa"]["forms"]["reason"],
            f"Expected 26 U.S.C. § 6012 citation in reason: {data['usa']['forms']['reason']!r}",
        )

    def test_de_outputs_still_trace_to_rule_outputs(self) -> None:
        # Invariant I2: every DE form-line value must trace to a
        # rule-graph output_fingerprint. The US block carrying
        # status=not_applicable does not contribute Decimal values, so
        # I2 is unaffected by the opt-out path.
        analysis_root = self.year_root / "outputs" / "analysis-steps"
        data = json.loads((analysis_root / "final-legal-output.json").read_text(encoding="utf-8"))
        provenance = data.get("_provenance")
        self.assertIsNotNone(provenance, "_provenance block must be present")
        # DE provenance must exist; US provenance is empty.
        rule_outputs = provenance.get("rule_outputs", {})
        self.assertIn("DE", rule_outputs)
        self.assertGreater(len(rule_outputs["DE"]), 0)
        self.assertEqual(rule_outputs.get("US", {}), {})

    def test_pub_514_derivation_is_skipped(self) -> None:
        # The Pub. 514 treaty dividend item derivation (DBA-USA
        # Art. 10/23) is U.S.-only; it must not run when the U.S.
        # pathway is disabled. The orchestrator emits an explicit
        # "Skipping" message rather than fabricating the per-Posten
        # CSV.
        self.assertIn(
            "Skipping Pub. 514 treaty dividend item derivation",
            self.stdout,
            f"Expected explicit Pub. 514 skip message in pipeline stdout: {self.stdout!r}",
        )


class UsFilingRequiredDefaultRegressionTest(unittest.TestCase):
    """Existing demo workspace must continue to produce identical
    output.

    Materializes the canonical demo-2025 workspace (where
    us_filing_required defaults to true) and asserts the headline
    Germany / U.S. numbers match the pre-change values. This is the
    "do not change DE legal math, do not change US legal math"
    invariant for the opt-out feature.
    """

    def test_default_demo_runs_and_produces_us_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            with redirect_stdout(io.StringIO()):
                run_year(root, "2025", workspace_root=paths.year_root)

            analysis_root = paths.year_root / "outputs" / "analysis-steps"
            data = json.loads((analysis_root / "final-legal-output.json").read_text(encoding="utf-8"))
            # Default-true posture in the demo workspace.
            self.assertIs(data["us_filing_required"], True)
            # U.S. side ran and produced the headline numbers.
            self.assertNotEqual(data["usa"]["forms"].get("status"), "not_applicable")
            us_estimate = data["usa"]["forms"]["tax_estimate"]
            # Same U.S.-source dividend conversion used by
            # ``tests/test_demo_workspace.py`` for byte-stable output.
            self.assertEqual(us_estimate["treaty_resourcing"]["us_source_dividends_usd"], "316.03")
            germany_results = data["germany"]["forms"]["results"]
            self.assertEqual(
                germany_results["capital"]["treaty_us_source_dividend_gross_eur"],
                "280.00",
            )


class UsFilingNotRequiredInconsistentPostureTest(unittest.TestCase):
    """Validation: opt-out posture with leftover U.S. inputs.

    A user who sets us_filing_required=false but leaves a populated
    us-tax-trace.csv (or other U.S. derived facts) on disk should be
    informed via validate_workspace that the U.S. block is now ignored.
    The engine still runs (us_filing_required wins), but the validator
    surfaces the inconsistency.
    """

    def test_validator_warns_when_us_filing_posture_set_with_required_false(self) -> None:
        from tax_pipeline.validate_workspace import build_validation_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = materialize_demo_workspace(root, demo_name="de-only-demo-2025", year=2025)
            # Re-write profile.json to keep usa.filing_posture populated
            # while us_filing_required=false — the inconsistent state
            # the test exercises.
            profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
            profile["jurisdictions"]["usa"]["filing_posture"] = "single"
            profile["elections"]["us_filing_required"] = False
            paths.profile_path.write_text(json.dumps(profile), encoding="utf-8")

            report = build_validation_report(paths)
            posture_lines = next(
                (lines for name, lines in report.sections if name == "Posture"),
                [],
            )
            joined = "\n".join(posture_lines)
            self.assertIn("us_filing_required: False", joined)
            self.assertIn("ignored under 26 U.S.C. § 6012", joined)


class PostureRegistryEngineSupportedTest(unittest.TestCase):
    """The ``elections.us_filing_required`` posture must report
    ``engine_supported=True`` now that the engine wires it through to
    the US/treaty/bridge gates.
    """

    def test_us_filing_required_is_engine_supported(self) -> None:
        field = next(
            (f for f in POSTURE_REGISTRY if f.key == "elections.us_filing_required"),
            None,
        )
        self.assertIsNotNone(field, "elections.us_filing_required must be in POSTURE_REGISTRY")
        self.assertTrue(
            field.engine_supported,
            "elections.us_filing_required must be engine_supported=True",
        )
        self.assertEqual(
            field.coming_soon_wave,
            "",
            "engine_supported postures must clear the coming_soon_wave annotation",
        )


class PostureEndpointPersistenceTest(unittest.TestCase):
    """POST elections.us_filing_required=false to /api/postures/state and
    verify the profile is updated."""

    def test_post_us_filing_required_false_is_persisted(self) -> None:
        from tax_pipeline.intake.server import dispatch_request
        from tax_pipeline.scaffold_year import ensure_year_scaffold
        from tax_pipeline.year_runtime import resolve_year_paths

        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            updated_state: dict[str, object] = {
                field.key: field.default for field in POSTURE_REGISTRY
            }
            updated_state["elections.us_filing_required"] = False

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/postures/state",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "state": updated_state,
                },
            )
            self.assertEqual(status, 200, payload)
            self.assertIs(payload["state"]["elections.us_filing_required"], False)

            # Profile.json on disk must reflect the opt-out.
            profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
            self.assertIs(profile["elections"]["us_filing_required"], False)


class CrossJurisdictionGateUnitTest(unittest.TestCase):
    """Unit tests for the gate helpers in cross_jurisdiction_2025."""

    def test_default_is_us_filing_required_true(self) -> None:
        self.assertTrue(read_us_filing_required({}))
        self.assertTrue(read_us_filing_required({"elections": {}}))

    def test_explicit_false_disables_us_pathway(self) -> None:
        profile = {"elections": {"us_filing_required": False}}
        self.assertFalse(read_us_filing_required(profile))
        self.assertFalse(should_include_us_2025_stages(profile))
        self.assertFalse(should_include_treaty_2025_stages(profile))
        self.assertFalse(should_include_bridge_2025_stages(profile))

    def test_string_false_coerces_correctly(self) -> None:
        # CSV-derived bool may surface as "false"/"true" strings.
        profile = {"elections": {"us_filing_required": "false"}}
        self.assertFalse(read_us_filing_required(profile))
        profile = {"elections": {"us_filing_required": "true"}}
        self.assertTrue(read_us_filing_required(profile))


class IsJurisdictionEnabledTest(unittest.TestCase):
    """Proposal 2: registry-driven enablement read.

    The U.S.-shaped helpers (``read_us_filing_required`` etc.) now
    delegate to :func:`is_jurisdiction_enabled` keyed by ISO-2 code.
    This generalises the gate to UK/CH/VN/IN once their registry
    rows land — the orchestrator doesn't need to learn a new
    function name per jurisdiction.
    """

    def test_us_enabled_by_default(self) -> None:
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        self.assertTrue(is_jurisdiction_enabled({}, "US"))
        self.assertTrue(is_jurisdiction_enabled({"elections": {}}, "US"))

    def test_us_explicit_false_disables(self) -> None:
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        profile = {"elections": {"us_filing_required": False}}
        self.assertFalse(is_jurisdiction_enabled(profile, "US"))

    def test_de_default_enabled(self) -> None:
        # Germany's enablement_default is True with no current opt-out
        # surface — the engine has no per-jurisdiction "Germany filing
        # not required" gate today, so the registry flag is a placeholder
        # that always evaluates to its default.
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        self.assertTrue(is_jurisdiction_enabled({}, "DE"))
        self.assertTrue(is_jurisdiction_enabled({"elections": {}}, "DE"))

    def test_unknown_jurisdiction_fails_closed(self) -> None:
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        with self.assertRaises(KeyError):
            is_jurisdiction_enabled({}, "XX")

    def test_iso_code_normalises_case(self) -> None:
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        self.assertEqual(
            is_jurisdiction_enabled({}, "us"),
            is_jurisdiction_enabled({}, "US"),
        )


if __name__ == "__main__":
    unittest.main()
