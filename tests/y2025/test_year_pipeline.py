from __future__ import annotations

import json
import os
import io
import subprocess
import tempfile
import unittest
import shutil
from types import SimpleNamespace
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock
import sys
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.analysis_inputs import (
    load_german_model_inputs,
    load_us_capital_inputs,
    load_us_model_inputs,
    missing_structured_inputs,
)
from tax_pipeline.classify import classify_relative_path
from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.forms import required_germany_form_paths, required_usa_form_paths
from tax_pipeline.legal_audit import required_germany_legal_audit_paths, required_usa_legal_audit_paths
from tax_pipeline.year_runtime import (
    active_year_paths,
    analysis_root,
    find_documents,
    manifest_path,
    resolve_workspace_root,
)
from tax_pipeline.manifest import build_manifest, write_manifest
from tax_pipeline.y2025.migrate import migrate_2025
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import write_final_legal_output_2025
from tax_pipeline.scaffold_year import (
    ensure_year_scaffold,
    main as scaffold_year_main,
    scaffold_year as run_scaffold_year,
)
from tax_pipeline.run_year import (
    analysis_inputs_directory,
    main as run_year_main,
    pipeline_modules,
    print_headline_summary,
    remove_obsolete_analysis_outputs,
    run_year,
)
from tax_pipeline.validate_workspace import main as validate_workspace_main


class YearPathsTest(unittest.TestCase):
    def test_year_paths_resolve_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()

            self.assertEqual(paths.year, 2025)
            self.assertEqual(paths.year_root, root / "years" / "2025")
            self.assertEqual(paths.raw_root, root / "years" / "2025" / "raw")
            self.assertEqual(paths.config_root, root / "years" / "2025" / "config")
            self.assertEqual(paths.normalized_root, root / "years" / "2025" / "normalized")
            self.assertEqual(paths.outputs_root, root / "years" / "2025" / "outputs")
            self.assertEqual(paths.analysis_root, root / "years" / "2025" / "outputs" / "analysis-steps")
            self.assertEqual(paths.forms_root, root / "years" / "2025" / "outputs" / "forms")
            self.assertEqual(paths.germany_forms_root, root / "years" / "2025" / "outputs" / "forms" / "germany")
            self.assertEqual(paths.usa_forms_root, root / "years" / "2025" / "outputs" / "forms" / "usa")
            self.assertEqual(paths.legal_audit_root, root / "years" / "2025" / "outputs" / "legal-audit")
            self.assertEqual(paths.germany_legal_audit_root, root / "years" / "2025" / "outputs" / "legal-audit" / "germany")
            self.assertEqual(paths.usa_legal_audit_root, root / "years" / "2025" / "outputs" / "legal-audit" / "usa")
            self.assertEqual(paths.manifest_path, root / "years" / "2025" / "normalized" / "documents.json")
            self.assertEqual(paths.profile_path, root / "years" / "2025" / "config" / "profile.json")
            self.assertEqual(paths.manual_overrides_path, root / "years" / "2025" / "config" / "manual_overrides.json")
            self.assertEqual(paths.people_path, root / "years" / "2025" / "config" / "people.csv")
            self.assertEqual(paths.payments_path, root / "years" / "2025" / "config" / "payments.csv")
            self.assertEqual(paths.elections_path, root / "years" / "2025" / "config" / "elections.csv")
            self.assertEqual(paths.manual_facts_root, root / "years" / "2025" / "normalized" / "manual-facts")
            self.assertEqual(paths.reference_data_root, root / "years" / "2025" / "normalized" / "reference-data")
            self.assertEqual(paths.derived_facts_root, root / "years" / "2025" / "normalized" / "derived-facts")
            self.assertEqual(paths.tax_positions_root, root / "years" / "2025" / "outputs" / "tax-positions")
            self.assertTrue((paths.raw_root / "real_estate").is_dir())
            self.assertTrue(paths.config_root.is_dir())
            self.assertTrue(paths.manual_facts_root.is_dir())
            self.assertTrue(paths.reference_data_root.is_dir())
            self.assertTrue(paths.derived_facts_root.is_dir())
            self.assertTrue(paths.tax_positions_root.is_dir())
            self.assertTrue(paths.forms_root.is_dir())
            self.assertTrue(paths.germany_forms_root.is_dir())
            self.assertTrue(paths.usa_forms_root.is_dir())
            self.assertTrue(paths.legal_audit_root.is_dir())
            self.assertTrue(paths.germany_legal_audit_root.is_dir())
            self.assertTrue(paths.usa_legal_audit_root.is_dir())

    def test_year_paths_can_resolve_external_workspace_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "repo"
            workspace_root = Path(tmp) / "external" / "2025"
            paths = YearPaths.for_workspace(project_root, workspace_root, 2025)
            paths.ensure_directories()

            self.assertEqual(paths.project_root, project_root)
            self.assertEqual(paths.workspace_root, workspace_root)
            self.assertEqual(paths.year_root, workspace_root)
            self.assertEqual(paths.raw_root, workspace_root / "raw")
            self.assertEqual(paths.config_root, workspace_root / "config")
            self.assertEqual(paths.outputs_root, workspace_root / "outputs")
            self.assertTrue(paths.analysis_root.is_dir())
            self.assertTrue(paths.usa_forms_root.is_dir())
            self.assertTrue(paths.germany_legal_audit_root.is_dir())


class ClassifierTest(unittest.TestCase):
    def test_classifier_recognizes_key_tax_documents(self) -> None:
        schwab = classify_relative_path(Path("brokers/1099 Composite and Year-End Summary - 2025_273.PDF"))
        coinbase = classify_relative_path(Path("crypto/coinbase-transactions-2025.csv"))
        lohn = classify_relative_path(Path("germany/person_2_Lohnsteuerbescheinigung_122025_260410_210646.pdf"))
        shareworks = classify_relative_path(Path("equity_comp/Shareworks/Statement (1).pdf"))

        self.assertEqual(schwab["doc_type"], "schwab_1099_pdf")
        self.assertEqual(schwab["provider"], "schwab")
        self.assertEqual(schwab["document_family"], "1099_composite")
        self.assertEqual(schwab["format"], "pdf")
        self.assertEqual(schwab["country_of_origin"], "US")
        self.assertEqual(schwab["tax_year"], 2025)
        self.assertEqual(coinbase["doc_type"], "coinbase_transactions_csv")
        self.assertEqual(coinbase["provider"], "coinbase")
        self.assertEqual(coinbase["document_family"], "transactions")
        self.assertEqual(coinbase["format"], "csv")
        self.assertEqual(coinbase["country_of_origin"], "US")
        self.assertEqual(coinbase["tax_year"], 2025)
        self.assertEqual(lohn["doc_type"], "german_lohnsteuer_pdf")
        self.assertEqual(lohn["provider"], "datev")
        self.assertEqual(lohn["document_family"], "lohnsteuerbescheinigung")
        self.assertEqual(lohn["format"], "pdf")
        self.assertEqual(lohn["country_of_origin"], "DE")
        self.assertEqual(lohn["owner"], "person_2")
        self.assertEqual(shareworks["doc_type"], "shareworks_statement_pdf")
        self.assertEqual(shareworks["provider"], "shareworks")
        self.assertEqual(shareworks["document_family"], "statement")
        self.assertEqual(shareworks["format"], "pdf")
        self.assertEqual(shareworks["country_of_origin"], "US")

    def test_classifier_handles_more_document_variants(self) -> None:
        donation = classify_relative_path(Path("receipts/Thanks for Donating to Example Charity Org.eml"))
        english_lohn = classify_relative_path(Path("germany/Certificate of wage tax deduction 2025 12 December.pdf"))
        us_1040 = classify_relative_path(Path("us/1040-2024-Alex-Example-final.pdf"))
        us_8879 = classify_relative_path(Path("us/8879-2024-Alex-Example-final.pdf"))
        n26_transfer = classify_relative_path(Path("us/TY2024-additional-6000.pdf"))
        social_notice = classify_relative_path(Path("us/person_2-social-2025.pdf"))
        schwab_limitations = classify_relative_path(Path("us/Schwab-limitations.png"))
        unknown_real_estate = classify_relative_path(Path("real_estate/closing-statement.pdf"))

        self.assertEqual(donation["doc_type"], "donation_receipt_eml")
        self.assertEqual(english_lohn["doc_type"], "german_lohnsteuer_pdf")
        self.assertEqual(us_1040["doc_type"], "us_1040_packet_pdf")
        self.assertEqual(us_1040["provider"], "tax_preparer")
        self.assertEqual(us_8879["doc_type"], "us_8879_pdf")
        self.assertEqual(us_8879["document_family"], "8879")
        self.assertEqual(n26_transfer["doc_type"], "n26_transfer_confirmation_pdf")
        self.assertEqual(n26_transfer["provider"], "n26")
        self.assertEqual(social_notice["doc_type"], "german_social_insurance_notice_pdf")
        self.assertEqual(social_notice["provider"], "germany_payroll")
        self.assertEqual(schwab_limitations["doc_type"], "schwab_limitation_image")
        self.assertEqual(unknown_real_estate["bucket"], "real_estate")
        self.assertEqual(unknown_real_estate["doc_type"], "unknown")


class ManifestTest(unittest.TestCase):
    def test_manifest_builds_deterministic_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "years" / "2025" / "raw"
            (raw / "brokers").mkdir(parents=True)
            (raw / "crypto").mkdir(parents=True)
            (raw / "germany").mkdir(parents=True)

            (raw / "brokers" / "1099 Composite and Year-End Summary - 2025_273.PDF").write_text("pdf placeholder")
            (raw / "crypto" / "coinbase-transactions-2025.csv").write_text("csv placeholder")
            (raw / "germany" / "ESt-Verlustvortrag-Bescheid 2024.pdf").write_text("pdf placeholder")

            manifest = build_manifest(raw, year=2025)

            self.assertEqual([entry["relative_path"] for entry in manifest], [
                "brokers/1099 Composite and Year-End Summary - 2025_273.PDF",
                "crypto/coinbase-transactions-2025.csv",
                "germany/ESt-Verlustvortrag-Bescheid 2024.pdf",
            ])
            self.assertEqual(manifest[0]["doc_type"], "schwab_1099_pdf")
            self.assertEqual(manifest[0]["provider"], "schwab")
            self.assertEqual(manifest[0]["document_family"], "1099_composite")
            self.assertEqual(manifest[0]["format"], "pdf")
            self.assertEqual(manifest[0]["country_of_origin"], "US")
            self.assertEqual(manifest[1]["doc_type"], "coinbase_transactions_csv")
            self.assertEqual(manifest[1]["provider"], "coinbase")
            self.assertEqual(manifest[1]["document_family"], "transactions")
            self.assertEqual(manifest[1]["format"], "csv")
            self.assertEqual(manifest[1]["country_of_origin"], "US")
            self.assertEqual(manifest[2]["doc_type"], "german_verlustvortrag_pdf")
            self.assertEqual(manifest[2]["provider"], "finanzamt")
            self.assertEqual(manifest[2]["document_family"], "verlustvortrag")
            self.assertEqual(manifest[2]["format"], "pdf")
            self.assertEqual(manifest[2]["country_of_origin"], "DE")

            json.dumps(manifest)

    def test_manifest_ignores_hidden_files_in_raw_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "years" / "2025" / "raw"
            (raw / "brokers").mkdir(parents=True)
            (raw / "brokers" / ".DS_Store").write_text("noise")
            (raw / "brokers" / "1099 Composite and Year-End Summary - 2025_273.PDF").write_text("pdf placeholder")

            manifest = build_manifest(raw, year=2025)

            self.assertEqual(len(manifest), 1)
            self.assertEqual(manifest[0]["relative_path"], "brokers/1099 Composite and Year-End Summary - 2025_273.PDF")

    def test_write_manifest_persists_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "years" / "2025" / "raw"
            manifest_path_target = root / "years" / "2025" / "normalized" / "documents.json"
            (raw / "crypto").mkdir(parents=True)
            (raw / "crypto" / "coinbase-transactions-2025.csv").write_text("csv placeholder")

            manifest = write_manifest(raw, manifest_path_target, year=2025)

            self.assertTrue(manifest_path_target.exists())
            self.assertEqual(json.loads(manifest_path_target.read_text()), manifest)


class YearRuntimeTest(unittest.TestCase):
    def test_active_year_paths_uses_explicit_workspace_root_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_path = root / "script.py"
            script_path.write_text("placeholder")

            workspace_root = root / "external" / "2025"
            with mock.patch.dict(
                os.environ,
                {"TAX_WORKSPACE_ROOT": str(workspace_root), "TAX_YEAR": "2025"},
                clear=False,
            ):
                paths = active_year_paths(script_path, default_year=2025)

            expected = (workspace_root / "outputs" / "analysis-steps").resolve()
            self.assertEqual(paths.analysis_root, expected)

    def test_resolve_workspace_root_uses_repo_local_demo_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "years" / "demo-2025").mkdir(parents=True)

            resolved = resolve_workspace_root(root, "demo-2025")

            self.assertEqual(resolved, (root / "years" / "demo-2025").resolve())

    def test_resolve_workspace_root_defaults_numeric_year_to_external_home_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_home = root / "home"
            fake_home.mkdir()

            with mock.patch("tax_pipeline.year_runtime.Path.home", return_value=fake_home):
                resolved = resolve_workspace_root(root, "2025")

            self.assertEqual(resolved, (fake_home / "taxes" / "2025").resolve())

    def test_resolve_workspace_root_prefers_explicit_workspace_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "custom-workspace"

            resolved = resolve_workspace_root(root, "2025", explicit_workspace=explicit)

            self.assertEqual(resolved, explicit.resolve())

    def test_find_documents_reads_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()

            doc = paths.raw_root / "crypto" / "coinbase-transactions-2025.csv"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("placeholder")
            paths.manifest_path.write_text(json.dumps([
                {
                    "relative_path": "crypto/coinbase-transactions-2025.csv",
                    "bucket": "crypto",
                    "doc_type": "coinbase_transactions_csv",
                    "tax_year": 2025,
                    "owner": None,
                    "confidence": "high",
                }
            ]))

            matches = find_documents(paths, doc_type="coinbase_transactions_csv", tax_year=2025)

            self.assertEqual(matches, [doc])

    def test_analysis_and_manifest_path_honor_overrides_and_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_path = root / "script.py"
            script_path.write_text("placeholder")
            custom_analysis = root / "custom-analysis"
            custom_manifest = root / "custom-manifest.json"

            with mock.patch.dict(
                os.environ,
                {
                    "TAX_ANALYSIS_DIR": str(custom_analysis),
                    "TAX_MANIFEST_PATH": str(custom_manifest),
                },
                clear=False,
            ):
                self.assertEqual(analysis_root(script_path), custom_analysis.resolve())
                self.assertEqual(manifest_path(script_path), custom_manifest.resolve())

            with mock.patch.dict(os.environ, {}, clear=True):
                expected_workspace = (Path.home() / "taxes" / "2025").resolve()
                self.assertEqual(
                    analysis_root(script_path),
                    expected_workspace / "outputs" / "analysis-steps",
                )
                self.assertEqual(
                    manifest_path(script_path),
                    expected_workspace / "normalized" / "documents.json",
                )

    def test_find_documents_filters_owner_and_returns_sorted_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()

            (paths.raw_root / "germany").mkdir(parents=True, exist_ok=True)
            doc1 = paths.raw_root / "germany" / "person_2_Lohnsteuerbescheinigung_122025_260410_210646.pdf"
            doc2 = paths.raw_root / "germany" / "Certificate of wage tax deduction 2025 12 December.pdf"
            doc1.write_text("person_2")
            doc2.write_text("person_1")
            paths.manifest_path.write_text(
                json.dumps(
                    [
                        {
                            "relative_path": "germany/Certificate of wage tax deduction 2025 12 December.pdf",
                            "bucket": "germany",
                            "doc_type": "german_lohnsteuer_pdf",
                            "tax_year": 2025,
                            "owner": "person_1",
                            "confidence": "high",
                        },
                        {
                            "relative_path": "germany/person_2_Lohnsteuerbescheinigung_122025_260410_210646.pdf",
                            "bucket": "germany",
                            "doc_type": "german_lohnsteuer_pdf",
                            "tax_year": 2025,
                            "owner": "person_2",
                            "confidence": "high",
                        },
                    ]
                )
            )

            matches = find_documents(paths, doc_type="german_lohnsteuer_pdf", tax_year=2025, owner="person_2")

            self.assertEqual(matches, [doc1])


class MigrationTest(unittest.TestCase):
    def test_migrate_2025_uses_existing_year_tree_as_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            raw_doc = paths.raw_root / "crypto" / "coinbase-transactions-2025.csv"
            raw_doc.parent.mkdir(parents=True, exist_ok=True)
            raw_doc.write_text("doc")

            returned = migrate_2025(root)

            self.assertEqual(returned.year_root, paths.year_root)
            self.assertTrue(paths.profile_path.exists())
            self.assertTrue(paths.manual_overrides_path.exists())
            self.assertTrue(paths.manifest_path.exists())
            manifest = json.loads(paths.manifest_path.read_text())
            self.assertEqual(manifest[0]["relative_path"], "crypto/coinbase-transactions-2025.csv")


class RunnerTest(unittest.TestCase):
    def _write_final_summary_output(
        self,
        paths: YearPaths,
        *,
        germany_results: dict,
        us_tax_estimate: dict | None = None,
        profile: dict | None = None,
    ) -> None:
        payload = {
            "schema_version": 1,
            "tax_year": paths.year,
            "source_role": "test final legal output consumed by print_headline_summary",
            "germany": {
                "forms": {
                    "profile": profile
                    or {
                        "jurisdictions": {
                            "germany": {"enabled": True},
                            "usa": {"enabled": True},
                        }
                    },
                    "results": germany_results,
                }
            },
            "usa": {
                "forms": {
                    "tax_estimate": us_tax_estimate or {},
                }
            },
        }
        (paths.analysis_root / "final-legal-output.json").write_text(json.dumps(payload))

    def test_print_headline_summary_writes_locked_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._write_final_summary_output(
                paths,
                germany_results={
                    "refunds": {"final_target_refund_eur": "3725.72"},
                    "vanilla_checkpoint": {"refund_or_balance_due_eur": "1200.00"},
                },
                us_tax_estimate={
                    "payments": {
                        "refund_if_positive_else_balance_due_usd": "428.64",
                        "refund_if_positive_else_balance_due_with_treaty_resourcing_usd": "1126.53",
                    },
                    "vanilla_checkpoint": {"refund_or_balance_due_usd": "314.15"},
                },
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print_headline_summary(paths)

            self.assertEqual(
                buffer.getvalue(),
                "\n".join(
                    [
                        "Year 2025 complete",
                        "  Germany refund: 3725.72 EUR",
                        "  Germany vanilla checkpoint refund: 1200.00 EUR",
                        "  U.S. base refund: 428.64 USD",
                        "  U.S. treaty refund: 1126.53 USD",
                        "  U.S. vanilla checkpoint refund: 314.15 USD",
                        "  Outputs: years/2025/outputs/analysis-steps",
                        "",
                    ]
                ),
            )

    def test_print_headline_summary_uses_balance_due_labels_for_negative_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._write_final_summary_output(
                paths,
                germany_results={
                    "refunds": {"final_target_refund_eur": "-12.34"},
                    "vanilla_checkpoint": {"refund_or_balance_due_eur": "-99.99"},
                },
                us_tax_estimate={
                    "payments": {
                        "refund_if_positive_else_balance_due_usd": "-428.64",
                        "refund_if_positive_else_balance_due_with_treaty_resourcing_usd": "-1126.53",
                    },
                    "vanilla_checkpoint": {"refund_or_balance_due_usd": "-314.15"},
                },
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print_headline_summary(paths)

            self.assertEqual(
                buffer.getvalue(),
                "\n".join(
                    [
                        "Year 2025 complete",
                        "  Germany balance due: 12.34 EUR",
                        "  Germany vanilla checkpoint balance due: 99.99 EUR",
                        "  U.S. base balance due: 428.64 USD",
                        "  U.S. treaty balance due: 1126.53 USD",
                        "  U.S. vanilla checkpoint balance due: 314.15 USD",
                        "  Outputs: years/2025/outputs/analysis-steps",
                        "",
                    ]
                ),
            )

    def test_print_headline_summary_uses_absolute_output_path_for_external_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "repo"
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(project_root, workspace_root, 2025)
            paths.ensure_directories()
            self._write_final_summary_output(
                paths,
                germany_results={
                    "refunds": {"final_target_refund_eur": "1.00"},
                    "vanilla_checkpoint": {"refund_or_balance_due_eur": "2.00"},
                },
                us_tax_estimate={
                    "payments": {
                        "refund_if_positive_else_balance_due_usd": "3.00",
                        "refund_if_positive_else_balance_due_with_treaty_resourcing_usd": "4.00",
                    },
                    "vanilla_checkpoint": {"refund_or_balance_due_usd": "5.00"},
                },
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print_headline_summary(paths)

            self.assertEqual(
                buffer.getvalue(),
                "\n".join(
                    [
                        "Year 2025 complete",
                        "  Germany refund: 1.00 EUR",
                        "  Germany vanilla checkpoint refund: 2.00 EUR",
                        "  U.S. base refund: 3.00 USD",
                        "  U.S. treaty refund: 4.00 USD",
                        "  U.S. vanilla checkpoint refund: 5.00 USD",
                        f"  Outputs: {paths.analysis_root}",
                        "",
                    ]
                ),
            )

    def test_print_headline_summary_skips_disabled_jurisdiction_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._write_final_summary_output(
                paths,
                profile={
                    "jurisdictions": {
                        "germany": {"enabled": True, "filing_posture": "single"},
                        "usa": {"enabled": False, "filing_posture": "single"},
                    }
                },
                germany_results={
                    "refunds": {"final_target_refund_eur": "3725.72"},
                    "vanilla_checkpoint": {"refund_or_balance_due_eur": "1200.00"},
                },
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print_headline_summary(paths)

            self.assertEqual(
                buffer.getvalue(),
                "\n".join(
                    [
                        "Year 2025 complete",
                        "  Germany refund: 3725.72 EUR",
                        "  Germany vanilla checkpoint refund: 1200.00 EUR",
                        "  Outputs: years/2025/outputs/analysis-steps",
                        "",
                    ]
                ),
            )

    def test_pipeline_modules_are_in_expected_order(self) -> None:
        # WS-5H (invariant migration plan §1.5): Pipeline 1 (Derivation)
        # runs FIRST so ``derived-facts.json`` / ``derivation-graph.json``
        # land before any Pipeline 2 module reads them.
        self.assertEqual(
            pipeline_modules(),
            [
                "tax_pipeline.pipelines.y2025.run_derivation",
                "tax_pipeline.pipelines.y2025.coinbase_private_sales",
                "tax_pipeline.pipelines.y2025.dher_german",
                "tax_pipeline.pipelines.y2025.germany_model",
                "tax_pipeline.pipelines.y2025.germany_elster_entry_sheet",
                "tax_pipeline.pipelines.y2025.us_capital_workpaper",
                "tax_pipeline.pipelines.y2025.us_model",
                "tax_pipeline.pipelines.y2025.us_treaty_packet",
                "tax_pipeline.pipelines.y2025.final_legal_output",
                "tax_pipeline.pipelines.y2025.rule_narratives",
                "tax_pipeline.pipelines.y2025.bilingual_summary",
                "tax_pipeline.pipelines.y2025.verbose_report",
            ],
        )

    def test_final_legal_output_module_main_resolves_active_year_paths(self) -> None:
        from tax_pipeline.pipelines.y2025 import final_legal_output

        paths = object()
        with (
            mock.patch.object(final_legal_output, "active_year_paths", return_value=paths) as mock_paths,
            mock.patch.object(final_legal_output, "write_final_legal_output_2025") as mock_write,
        ):
            final_legal_output.main()

        mock_paths.assert_called_once_with(Path(final_legal_output.__file__), default_year=2025)
        mock_write.assert_called_once_with(paths)

    def test_remove_obsolete_analysis_outputs_deletes_numbered_active_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis_root = root / "years" / "2025" / "outputs" / "analysis-steps"
            analysis_root.mkdir(parents=True)
            obsolete = analysis_root / "091-model-results.json"
            obsolete.write_text("old")
            bridge = analysis_root / "067-ecb-usd-eur-daily-2022-2025.csv"
            bridge.write_text("old")
            stale_treaty_bridge = analysis_root / "de-us-treaty-dividend-packet.json"
            stale_treaty_bridge.write_text("old")
            readable = analysis_root / "germany-model-results.json"
            readable.write_text("new")

            remove_obsolete_analysis_outputs(analysis_root)

            self.assertFalse(obsolete.exists())
            self.assertFalse(bridge.exists())
            self.assertFalse(stale_treaty_bridge.exists())
            self.assertTrue(readable.exists())

    def test_readable_analysis_outputs_use_readable_names(self) -> None:
        from tax_pipeline.pipelines.y2025 import coinbase_private_sales as coinbase
        from tax_pipeline.pipelines.y2025 import dher_german as dher
        from tax_pipeline.pipelines.y2025 import germany_elster_entry_sheet as elster
        from tax_pipeline.pipelines.y2025 import germany_model as germany
        from tax_pipeline.pipelines.y2025 import us_capital_workpaper as us_capital
        from tax_pipeline.pipelines.y2025 import us_model
        from tax_pipeline.pipelines.y2025 import us_treaty_packet as treaty
        from tax_pipeline.pipelines.y2025 import verbose_report

        self.assertEqual(coinbase.LOT_DETAIL_CSV.name, "crypto-private-sales-lot-detail.csv")
        self.assertEqual(coinbase.DISPOSITIONS_CSV.name, "crypto-private-sales-dispositions.csv")
        self.assertEqual(coinbase.SUMMARY_MD.name, "crypto-private-sales-summary.md")
        self.assertEqual(coinbase.RESULTS_JSON.name, "crypto-private-sales-results.json")
        self.assertEqual(dher.DETAIL_CSV.name, "germany-dher-capital-detail.csv")
        self.assertEqual(dher.RESULTS_JSON.name, "germany-dher-results.json")
        self.assertEqual(dher.SUMMARY_MD.name, "germany-dher-summary.md")
        self.assertEqual(germany.RESULTS_JSON.name, "germany-model-results.json")
        self.assertEqual(germany.TRACE_CSV.name, "germany-model-trace.csv")
        self.assertEqual(germany.SUMMARY_MD.name, "germany-summary.md")
        self.assertEqual(elster.KAP_SUMMARY_CSV.name, "germany-kap-summary.csv")
        self.assertEqual(elster.N_BREAKDOWN_CSV.name, "germany-n-work-expenses.csv")
        self.assertEqual(elster.KAP_INV_FUND_CSV.name, "germany-kap-inv-fund-summary.csv")
        self.assertEqual(elster.ENTRY_MD.name, "germany-elster-entry-sheet.md")
        self.assertEqual(elster.PERSON_2_BANK_SUMMARY_MD.name, "spouse-bank-capital-certificate-summary.md")
        self.assertEqual(us_capital.BUCKETS_CSV.name, "us-form-8949-income-buckets.csv")
        self.assertEqual(us_capital.RESULTS_JSON.name, "us-capital-results.json")
        self.assertEqual(us_capital.SUMMARY_MD.name, "us-capital-summary.md")
        self.assertEqual(us_model.RESULTS_JSON.name, "us-tax-estimate.json")
        self.assertEqual(us_model.SUMMARY_MD.name, "us-tax-estimate.md")
        self.assertEqual(us_model.TRACE_CSV.name, "us-tax-trace.csv")
        self.assertEqual(us_model.AUDIT_NOTE_MD.name, "us-audit-note.md")
        self.assertEqual(treaty.PACKET_JSON.name, "us-treaty-package.json")
        self.assertEqual(treaty.WORKSHEET_CSV.name, "us-treaty-resourcing-worksheet.csv")
        self.assertEqual(treaty.ENTRY_MD.name, "us-treaty-entry-sheet.md")
        self.assertEqual(treaty.STATEMENTS_MD.name, "us-supporting-statements.md")
        self.assertEqual(verbose_report.VERBOSE_MD.name, "verbose-report.md")

    def test_coinbase_private_sale_carryforward_uses_prior_loss_against_current_gain(self) -> None:
        from tax_pipeline.pipelines.y2025.coinbase_private_sales import (
            compute_private_sale_carryforward_2025,
        )

        # § 23 Abs. 3 Sätze 7 bis 9 EStG allows private-sale losses only inside
        # the private-sale bucket. A prior carryforward is consumed by positive
        # current-year § 23 gains before any remaining carryforward is reported.
        result = compute_private_sale_carryforward_2025(
            prior_carryforward_eur=Decimal("869.00"),
            current_private_sale_result_eur=Decimal("100.00"),
        )

        self.assertEqual(result["prior_private_sale_carryforward_eur"], Decimal("869.00"))
        self.assertEqual(result["carryforward_used_in_2025_eur"], Decimal("100.00"))
        self.assertEqual(result["updated_private_sale_carryforward_eur"], Decimal("769.00"))

    def test_coinbase_private_sale_carryforward_adds_current_year_private_sale_loss(self) -> None:
        from tax_pipeline.pipelines.y2025.coinbase_private_sales import (
            compute_private_sale_carryforward_2025,
        )

        # § 23 Abs. 3 Sätze 7 bis 9 EStG carries unused private-sale losses
        # forward within the same bucket when current-year § 23 result is negative.
        result = compute_private_sale_carryforward_2025(
            prior_carryforward_eur=Decimal("869.00"),
            current_private_sale_result_eur=Decimal("-50.00"),
        )

        self.assertEqual(result["carryforward_used_in_2025_eur"], Decimal("0.00"))
        self.assertEqual(result["updated_private_sale_carryforward_eur"], Decimal("919.00"))

    def test_germany_model_rejects_married_separate_filing_surface(self) -> None:
        from tax_pipeline.pipelines.y2025 import germany_model as germany

        with (
            mock.patch.object(germany, "load_inputs", return_value={}),
            mock.patch.object(germany, "load_coinbase_results", return_value={}),
            mock.patch.object(germany, "load_dher_results", return_value={}),
            mock.patch.object(germany, "load_fund_classification", return_value={}),
            mock.patch.object(germany, "compute_capital_buckets", return_value=SimpleNamespace()),
            mock.patch.object(germany, "load_joint_ordinary_inputs_2025", return_value=object()),
            mock.patch.object(
                germany,
                "compute_joint_ordinary_assessment_2025",
                return_value=SimpleNamespace(filing_posture="married_separate", people=()),
            ),
            mock.patch.object(germany, "compute_germany_vanilla_checkpoint_2025", return_value=SimpleNamespace()),
        ):
            with self.assertRaisesRegex(
                NotImplementedError,
                "married_separate.*not supported",
            ):
                germany.main()

    def test_germany_model_consults_posture_registry(self) -> None:
        from tax_pipeline.pipelines.y2025 import germany_model as germany

        ordinary_assessment = SimpleNamespace(
            filing_posture="single",
            people=[SimpleNamespace(slot="person_1")],
            income_tax_eur=Decimal("0.00"),
            solidarity_surcharge_eur=Decimal("0.00"),
            total_tax_before_credits_eur=Decimal("0.00"),
            total_credits_eur=Decimal("0.00"),
            refund_or_balance_due_eur=Decimal("0.00"),
            taxable_income_eur=Decimal("0.00"),
        )

        with (
            mock.patch.object(germany, "load_joint_ordinary_inputs_2025", return_value=object()),
            mock.patch.object(germany, "compute_joint_ordinary_assessment_2025", return_value=ordinary_assessment),
            mock.patch.object(germany, "load_inputs", return_value={"saver_allowance_eur": Decimal("1000.00")}),
            mock.patch.object(
                germany,
                "load_coinbase_results",
                return_value={
                    "private_sale_result_eur": Decimal("0.00"),
                    "prior_private_sale_carryforward_eur": Decimal("0.00"),
                    "updated_private_sale_carryforward_eur": Decimal("0.00"),
                },
            ),
            mock.patch.object(germany, "load_dher_results", return_value={"total_gain_eur": Decimal("0.00")}),
            mock.patch.object(germany, "load_fund_classification", return_value={}),
            mock.patch.object(germany, "compute_capital_buckets", side_effect=RuntimeError("stop after posture lookup")),
            mock.patch.object(germany, "compute_germany_vanilla_checkpoint_2025", return_value=SimpleNamespace()),
            mock.patch("tax_pipeline.pipelines.y2025.germany_model.get_posture_definition", create=True) as mocked,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after posture lookup"):
                germany.main()

        mocked.assert_called_once_with("germany", "single")

    def test_usa_model_consults_posture_registry(self) -> None:
        from tax_pipeline.pipelines.y2025 import us_model

        assessment_inputs = SimpleNamespace(
            profile=SimpleNamespace(
                filing_status_label="Single",
                spouse_name_for_mfs_line="",
            ),
            capital_facts=SimpleNamespace(estimated_payment_2025_usd=Decimal("0.00")),
        )

        with (
            mock.patch.object(us_model, "load_us_assessment_inputs_2025", return_value=assessment_inputs),
            mock.patch.object(us_model, "compute_us_assessment_2025", side_effect=RuntimeError("stop after posture lookup")),
            mock.patch.object(us_model, "compute_usa_vanilla_checkpoint_2025", return_value=SimpleNamespace()),
            mock.patch("tax_pipeline.pipelines.y2025.us_model.get_posture_definition", create=True) as mocked,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after posture lookup"):
                us_model.main()

        mocked.assert_called_once_with("usa", "single")

    def test_missing_structured_inputs_reports_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()

            (paths.reference_data_root / "ecb-usd-eur-daily.csv").write_text("ok")

            missing = [path.as_posix() for path in missing_structured_inputs(paths)]

            self.assertIn("normalized/derived-facts/germany/capital-sales-detail.csv", missing)
            self.assertIn("outputs/tax-positions/de-model-assumptions.csv", missing)

    def test_analysis_inputs_directory_returns_analysis_root_without_writing_bridge_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(json.dumps({"profile": "test"}))
            paths.manual_overrides_path.write_text(
                json.dumps(
                    {
                        "treaty_resourcing": {"enabled": None, "notes": ""},
                        "fund_classification": {"aktienfonds": [], "non_aktienfonds": []},
                        "equity_comp": {"rsu_wage_in_payroll": None, "basis_overrides": []},
                        "deductions": {"persons": {}, "work_use_percentages": {"management_book": "1.00"}},
                        "carryovers": {"german": {}, "us_ftc": {}},
                    }
                )
            )
            (paths.reference_data_root / "ecb-usd-eur-daily.csv").write_text("DATE,VALUE\n")
            (paths.reference_data_root / "de-tax-constants.csv").write_text(
                "section,key,value,source,note\n"
                "base,saver_allowance_eur,2000.00,src,note\n"
                "base,capital_tax_rate,0.25,src,note\n"
                "base,soli_rate,0.055,src,note\n"
                "base,other_income_22nr3_freigrenze_eur,256.00,src,note\n"
            )
            (paths.reference_data_root / "us-tax-constants.csv").write_text(
                "section,key,value,source,note\nirs,standard_deduction_2025_usd,15750.00,src,note\n"
            )
            (paths.facts_root / "de-spouse-bank-capital-certificate.csv").write_text(
                "section,key,value,source,note\nspouse_bank_capital,person_2_bank_certificate_kap_income_eur,1.00,src,note\n"
            )
            (paths.facts_root / "de-loss-carryforwards.csv").write_text(
                "section,key,value,source,note\ncarryforward,stock_loss_carryforward_2024_eur,2.00,src,note\n"
            )
            (paths.facts_root / "de-equipment-source-facts.csv").write_text(
                "section,key,value,source,note\nequipment,management_book_amount_eur,26.74,src,note\n"
            )
            (paths.facts_root / "us-carryovers-and-payments.csv").write_text(
                "section,key,value,source,note\npayment,estimated_payment_2025_usd,2000.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "income-summary.csv").write_text(
                "section,key,value,source,note\nschedule_b,ordinary_dividends_usd,10.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "foreign-wage-support.csv").write_text(
                "section,key,value,source,note\ngerman,taxpayer_gross_wages_eur,100.00,src,note\n"
            )
            (paths.derived_facts_root / "germany" / "capital-sales-detail.csv").write_text("date,action,symbol\n")
            (paths.derived_facts_root / "germany" / "income-cashflows.csv").write_text("date,action,kind\n")
            (paths.derived_facts_root / "germany" / "capital-support.csv").write_text(
                "section,key,value,source,note\nbase,foreign_tax_1099_eur,44.35,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "capital-summary.csv").write_text(
                "section,key,value,source,note\ncapital,schwab_short_box_a_gain_usd,1.00,src,note\n"
            )
            (paths.derived_facts_root / "common" / "other-income-facts.csv").write_text(
                "section,key,value,source,note\nother_income,staking_income_usd,2.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "ftc-support.csv").write_text(
                "section,key,value,source,note\ngerman,joint_wage_side_tax_eur,3.00,src,note\n"
            )
            (paths.tax_positions_root / "de-model-assumptions.csv").write_text(
                "section,key,value,source,note\nbase,treaty_dividend_credit_eur,4.00,src,note\n"
            )
            (paths.tax_positions_root / "us-model-assumptions.csv").write_text(
                "section,key,value,source,note\nassumption,include_staking_in_niit,1,src,note\n"
            )

            copied_to = analysis_inputs_directory(root, 2025, workspace_root=paths.workspace_root)

            self.assertEqual(copied_to, paths.analysis_root.resolve())
            self.assertFalse((paths.analysis_root / "067-ecb-usd-eur-daily-2022-2025.csv").exists())
            self.assertFalse((paths.analysis_root / "090-model-inputs.csv").exists())
            self.assertFalse((paths.analysis_root / "120-us-2025-capital-inputs.csv").exists())
            self.assertFalse((paths.analysis_root / "124-us-2025-tax-model-inputs.csv").exists())

    def test_direct_structured_loaders_match_model_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            paths.profile_path.write_text(json.dumps({"profile": "test"}))
            paths.manual_overrides_path.write_text(
                json.dumps(
                    {
                        "treaty_resourcing": {"enabled": None, "notes": ""},
                        "fund_classification": {"aktienfonds": [], "non_aktienfonds": []},
                        "equity_comp": {"rsu_wage_in_payroll": None, "basis_overrides": []},
                        "deductions": {"persons": {}, "work_use_percentages": {"management_book": "1.00"}},
                        "carryovers": {"german": {}, "us_ftc": {}},
                    }
                )
            )
            (paths.reference_data_root / "de-tax-constants.csv").write_text(
                "section,key,value,source,note\n"
                "base,saver_allowance_eur,2000.00,src,note\n"
                "base,capital_tax_rate,0.25,src,note\n"
            )
            (paths.reference_data_root / "us-tax-constants.csv").write_text(
                "section,key,value,source,note\nirs,standard_deduction_2025_usd,15750.00,src,note\n"
            )
            (paths.facts_root / "de-spouse-bank-capital-certificate.csv").write_text(
                "section,key,value,source,note\nspouse_bank_capital,person_2_bank_certificate_kap_income_eur,1.00,src,note\n"
            )
            (paths.facts_root / "de-loss-carryforwards.csv").write_text(
                "section,key,value,source,note\ncarryforward,stock_loss_carryforward_2024_eur,2.00,src,note\n"
            )
            (paths.facts_root / "de-equipment-source-facts.csv").write_text(
                "section,key,value,source,note\nequipment,management_book_amount_eur,26.74,src,note\n"
            )
            (paths.facts_root / "us-carryovers-and-payments.csv").write_text(
                "section,key,value,source,note\npayment,estimated_payment_2025_usd,2000.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "income-summary.csv").write_text(
                "section,key,value,source,note\nschedule_b,ordinary_dividends_usd,10.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "foreign-wage-support.csv").write_text(
                "section,key,value,source,note\ngerman,taxpayer_gross_wages_eur,100.00,src,note\n"
            )
            (paths.derived_facts_root / "common" / "other-income-facts.csv").write_text(
                "section,key,value,source,note\nother_income,staking_income_usd,2.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "capital-summary.csv").write_text(
                "section,key,value,source,note\ncapital,schwab_short_box_a_gain_usd,1.00,src,note\n"
            )
            (paths.derived_facts_root / "usa" / "ftc-support.csv").write_text(
                "section,key,value,source,note\ngerman,joint_wage_side_tax_eur,3.00,src,note\n"
            )
            (paths.tax_positions_root / "de-model-assumptions.csv").write_text(
                "section,key,value,source,note\nbase,treaty_dividend_credit_eur,4.00,src,note\n"
            )
            (paths.tax_positions_root / "us-model-assumptions.csv").write_text(
                "section,key,value,source,note\nassumption,include_staking_in_niit,1,src,note\n"
            )

            de_inputs = load_german_model_inputs(paths)
            us_capital = load_us_capital_inputs(paths)
            us_model = load_us_model_inputs(paths)

            self.assertEqual(str(de_inputs["management_book_work_share"]), "1.00")
            self.assertEqual(str(de_inputs["treaty_dividend_credit_eur"]), "4.00")
            self.assertEqual(str(us_capital["estimated_payment_2025_usd"]), "2000.00")
            self.assertEqual(str(us_model["taxpayer_gross_wages_eur"]), "100.00")

    def test_load_german_model_inputs_fails_when_equipment_work_share_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            paths.manual_overrides_path.write_text(
                json.dumps(
                    {
                        "deductions": {
                            "work_use_percentages": {},
                            "persons": {
                                "person_1": {
                                    "home_office_days_without_first_workplace_visit": 0,
                                    "home_office_days_with_first_workplace_visit": 0,
                                    "manual_work_equipment_deduction_eur": "0.00",
                                    "telecom_deduction_eur": "0.00",
                                    "cross_border_tax_help_deduction_eur": "0.00",
                                    "employment_legal_insurance_deduction_eur": "0.00",
                                    "health_insurance_sick_pay_reduction_rate": "0.04",
                                    "work_equipment_items": ["charger"],
                                },
                                "person_2": {
                                    "home_office_days_without_first_workplace_visit": 0,
                                    "home_office_days_with_first_workplace_visit": 0,
                                    "manual_work_equipment_deduction_eur": "0.00",
                                    "telecom_deduction_eur": "0.00",
                                    "cross_border_tax_help_deduction_eur": "0.00",
                                    "employment_legal_insurance_deduction_eur": "0.00",
                                    "health_insurance_sick_pay_reduction_rate": "0.04",
                                    "work_equipment_items": [],
                                },
                            },
                        }
                    }
                )
            )
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "taxpayer": {"name": "Demo Taxpayer"},
                        "spouse": {"name": "Demo Spouse"},
                        "german_return": {"assume_joint_assessment_if_married": True},
                    }
                )
            )
            (paths.facts_root / "de-equipment-source-facts.csv").write_text(
                "section,key,value,source,note\n"
                "equipment,charger_amount_eur,100.00,manual,charger\n"
            )

            with self.assertRaisesRegex(
                ValueError,
                "Missing work-use percentages for configured equipment items in manual_overrides.json: charger",
            ):
                load_german_model_inputs(paths)

    def test_run_year_executes_all_scripts_with_year_layout_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths) as mock_resolve,
                mock.patch("tax_pipeline.run_year.write_manifest") as mock_manifest,
                mock.patch("tax_pipeline.run_year.extract_all_facts") as mock_extract_facts,
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root) as mock_seed,
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs") as mock_cleanup,
                mock.patch("tax_pipeline.run_year._run_pipeline_module") as mock_module_runner,
                mock.patch("tax_pipeline.run_year.ensure_required_paths"),
                mock.patch("tax_pipeline.run_year.render_germany_forms"),
                mock.patch("tax_pipeline.run_year.render_usa_forms"),
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit"),
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit"),
                mock.patch("tax_pipeline.run_year.print_headline_summary") as mock_summary,
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # already mock ``print_headline_summary``.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025")

            mock_resolve.assert_called_once_with(root, "2025", workspace_root=None)
            self.assertEqual(mock_manifest.call_count, 1)
            mock_extract_facts.assert_called_once_with(paths)
            mock_seed.assert_called_once_with(root, "2025", workspace_root=None)
            self.assertEqual(mock_module_runner.call_count, len(pipeline_modules()))
            mock_summary.assert_called_once_with(paths)
            mock_cleanup.assert_called_once_with(paths.analysis_root)
            first_call = mock_module_runner.call_args_list[0]
            env = first_call.kwargs["env"]
            self.assertEqual(env["TAX_YEAR"], "2025")
            self.assertEqual(env["TAX_WORKSPACE_ROOT"], str(paths.workspace_root))
            self.assertEqual(env["TAX_USE_YEAR_LAYOUT"], "1")
            self.assertEqual(env["TAX_ANALYSIS_DIR"], str(paths.analysis_root))
            self.assertEqual(first_call.args[0], pipeline_modules()[0])

    def test_run_year_rejects_invalid_profile_json_before_module_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text("{not valid json")
            paths.manual_overrides_path.write_text("{}")

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year._run_pipeline_module") as mock_module_runner,
            ):
                with self.assertRaisesRegex(ValueError, "Invalid JSON in .*profile.json"):
                    run_year(root, "2025")

            mock_module_runner.assert_not_called()

    def test_run_year_rejects_invalid_manual_overrides_json_before_module_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {
                            "germany": {"enabled": True, "filing_posture": "single"},
                            "usa": {"enabled": False, "filing_posture": "single"},
                        }
                    }
                )
            )
            paths.manual_overrides_path.write_text("{not valid json")

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year._run_pipeline_module") as mock_module_runner,
            ):
                with self.assertRaisesRegex(ValueError, "Invalid JSON in .*manual_overrides.json"):
                    run_year(root, "2025")

            mock_module_runner.assert_not_called()

    def test_run_year_defaults_numeric_year_to_external_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths) as mock_resolve,
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
                mock.patch("tax_pipeline.run_year._run_pipeline_module"),
                mock.patch("tax_pipeline.run_year.ensure_required_paths"),
                mock.patch("tax_pipeline.run_year.render_germany_forms"),
                mock.patch("tax_pipeline.run_year.render_usa_forms"),
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit"),
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # already mock ``print_headline_summary``.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025")

            mock_resolve.assert_called_once_with(root, "2025", workspace_root=None)

    def test_run_year_uses_explicit_workspace_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "custom-workspace"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths) as mock_resolve,
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
                mock.patch("tax_pipeline.run_year._run_pipeline_module"),
                mock.patch("tax_pipeline.run_year.ensure_required_paths"),
                mock.patch("tax_pipeline.run_year.render_germany_forms"),
                mock.patch("tax_pipeline.run_year.render_usa_forms"),
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit"),
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # already mock ``print_headline_summary``.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025", workspace_root=workspace_root)

            mock_resolve.assert_called_once_with(root, "2025", workspace_root=workspace_root)

    def test_main_accepts_demo_workspace_token(self) -> None:
        with mock.patch("tax_pipeline.run_year.run_year") as mock_run:
            run_year_main(["demo-2025"])

        project_root = Path(__file__).resolve().parents[2]
        mock_run.assert_called_once_with(project_root, "demo-2025", workspace_root=None, prompt_if_config_missing=True)

    def test_main_accepts_explicit_workspace_override(self) -> None:
        workspace_root = Path("/tmp/example-workspace")

        with mock.patch("tax_pipeline.run_year.run_year") as mock_run:
            run_year_main(["2025", "--workspace", str(workspace_root)])

        project_root = Path(__file__).resolve().parents[2]
        mock_run.assert_called_once_with(project_root, "2025", workspace_root=workspace_root, prompt_if_config_missing=True)

    def test_run_year_invokes_country_form_renderers_for_2025(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            for required in (
                required_germany_form_paths(paths)
                + required_usa_form_paths(paths)
                + required_germany_legal_audit_paths(paths)
                + required_usa_legal_audit_paths(paths)
            ):
                required.parent.mkdir(parents=True, exist_ok=True)
                required.write_text("ready")

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year._run_pipeline_module"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
                mock.patch("tax_pipeline.run_year.render_germany_forms") as mock_render_germany,
                mock.patch("tax_pipeline.run_year.render_usa_forms") as mock_render_usa,
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit") as mock_render_germany_audit,
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit") as mock_render_usa_audit,
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # mock the form renderers above.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025")

            mock_render_germany.assert_called_once_with(paths)
            mock_render_usa.assert_called_once_with(paths)
            mock_render_germany_audit.assert_called_once_with(paths)
            mock_render_usa_audit.assert_called_once_with(paths)

    def test_run_year_raises_when_final_legal_output_is_missing_for_2025(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year._run_pipeline_module"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
            ):
                with self.assertRaises(FileNotFoundError) as cm:
                    run_year(root, "2025")

            self.assertIn("final-legal-output.json", str(cm.exception))

    def test_run_year_raises_when_final_legal_output_is_invalid_for_2025(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            (paths.analysis_root / "final-legal-output.json").write_text("ready")

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year._run_pipeline_module"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
            ):
                with self.assertRaises(ValueError) as cm:
                    run_year(root, "2025")

            self.assertIn("Invalid final legal output JSON", str(cm.exception))

    def test_final_output_requires_germany_core_form_projection_for_2025(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            (paths.analysis_root / "germany-model-results.json").write_text(
                json.dumps(
                    {
                        "refunds": {
                            "final_target_refund_eur": "0.00",
                            "other_income_22nr3_eur": "0.00",
                            "equipment_work_share_total_eur": "0.00",
                        },
                        "ordinary": {"zve_eur": "0.00"},
                        "capital": {
                            "capital_tax_with_teilfreistellung_after_treaty_eur": "0.00",
                            "dher_stock_gain_eur": "0.00",
                        },
                        "vanilla_checkpoint": {"refund_or_balance_due_eur": "0.00"},
                    }
                )
            )
            (paths.analysis_root / "germany-model-trace.csv").write_text(
                "step_code,description,value_eur,legal_reference,authority_url\n"
                "ordinary.refund,Final refund target,0.00,§ 36 EStG,https://example.com\n"
            )
            (paths.analysis_root / "germany-audit-note.md").write_text(
                "## Overview\nSynthetic Germany legal audit.\n\n"
                "## Manual Filing Positions\n- None.\n"
            )
            (paths.analysis_root / "germany-summary.md").write_text("Germany summary\n")
            (paths.analysis_root / "germany-kap-summary.csv").write_text(
                "owner,line,value_eur,source,notes\nperson_1,17,0.00,synthetic,none\n"
            )
            (paths.analysis_root / "germany-n-work-expenses.csv").write_text(
                "form,line,label,amount_eur,source\nAnlage N (Person 1),54-56,Work items,0.00,synthetic\n"
            )
            (paths.analysis_root / "germany-kap-inv-fund-summary.csv").write_text(
                "line,value_eur,source,notes\n4,0.00,synthetic,none\n"
            )
            (paths.analysis_root / "germany-elster-entry-sheet.md").write_text("Germany ELSTER entry sheet\n")

            paths.profile_path.write_text(
                json.dumps(
                    {
                        "taxpayer": {"name": "Demo Taxpayer"},
                        "spouse": {"name": "Demo Spouse"},
                        "german_return": {"assume_joint_assessment_if_married": True},
                    }
                )
            )
            (paths.tax_positions_root / "de-model-assumptions.csv").write_text(
                "section,key,value,source,note\nbase,treaty_dividend_credit_eur,0.00,synthetic,none\n"
            )
            with self.assertRaises(FileNotFoundError) as cm:
                write_final_legal_output_2025(paths)

            self.assertIn("render_projection.elster.anlage_n_entries_by_slot", str(cm.exception))

    def test_run_year_raises_when_usa_structured_inputs_are_missing_for_2025(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            missing_name = "us-tax-constants.csv"
            profile = json.loads(paths.profile_path.read_text())
            profile["jurisdictions"]["germany"]["enabled"] = False
            profile["jurisdictions"]["usa"]["enabled"] = True
            paths.profile_path.write_text(json.dumps(profile))
            (paths.reference_data_root / missing_name).unlink()

            with self.assertRaises(FileNotFoundError) as cm:
                with redirect_stdout(io.StringIO()):
                    run_year(root, "2025", workspace_root=paths.year_root)

            self.assertIn(missing_name, str(cm.exception))

    def test_validate_workspace_reports_grouped_missing_structured_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2026"
            paths = YearPaths.for_workspace(root, workspace_root, 2026)
            ensure_year_scaffold(paths)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = validate_workspace_main(["2026", "--workspace", str(workspace_root)])

            output = stdout.getvalue()
            self.assertEqual(exit_code, 1)
            self.assertIn("Workspace", output)
            self.assertIn("Config", output)
            self.assertIn("Structured Inputs", output)
            self.assertIn("normalized/reference-data/de-tax-constants.csv", output)
            self.assertIn("NOT READY", output)

    def test_validate_workspace_main_accepts_demo_workspace_token(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = validate_workspace_main(["demo-2025"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("demo-2025", output)
        self.assertIn("READY", output)

    def test_run_year_preserves_existing_outputs_when_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()
            obsolete = paths.analysis_root / "091-model-results.json"
            obsolete.write_text("old")

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs") as mock_cleanup,
                mock.patch(
                    "tax_pipeline.run_year._run_pipeline_module",
                    side_effect=subprocess.CalledProcessError(1, ["script"]),
                ),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # already mock ``print_headline_summary``.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    run_year(root, "2025")

            mock_cleanup.assert_not_called()
            self.assertTrue(obsolete.exists())

    def test_run_year_passes_prompt_flag_to_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold") as mock_scaffold,
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year._run_pipeline_module"),
                mock.patch("tax_pipeline.run_year.ensure_required_paths"),
                mock.patch("tax_pipeline.run_year.render_germany_forms"),
                mock.patch("tax_pipeline.run_year.render_usa_forms"),
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit"),
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # already mock ``print_headline_summary``.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025", prompt_if_config_missing=True)

            mock_scaffold.assert_called_once_with(paths, prompt_if_config_missing=True)

    def test_run_year_skips_usa_modules_and_renderers_when_usa_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {
                            "germany": {"enabled": True, "filing_posture": "single"},
                            "usa": {"enabled": False, "filing_posture": "single"},
                        }
                    }
                )
            )

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
                mock.patch("tax_pipeline.run_year._run_pipeline_module") as mock_module_runner,
                mock.patch("tax_pipeline.run_year.ensure_required_paths"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                mock.patch("tax_pipeline.run_year.render_germany_forms") as mock_render_germany,
                mock.patch("tax_pipeline.run_year.render_usa_forms") as mock_render_usa,
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit") as mock_render_germany_audit,
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit") as mock_render_usa_audit,
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # mock the form renderers above.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025")

            called_modules = [call.args[0] for call in mock_module_runner.call_args_list]
            self.assertIn("tax_pipeline.pipelines.y2025.germany_model", called_modules)
            self.assertIn("tax_pipeline.pipelines.y2025.germany_elster_entry_sheet", called_modules)
            self.assertNotIn("tax_pipeline.pipelines.y2025.us_capital_workpaper", called_modules)
            self.assertNotIn("tax_pipeline.pipelines.y2025.us_model", called_modules)
            self.assertNotIn("tax_pipeline.pipelines.y2025.us_treaty_packet", called_modules)
            mock_render_germany.assert_called_once_with(paths)
            mock_render_usa.assert_not_called()
            mock_render_germany_audit.assert_called_once_with(paths)
            mock_render_usa_audit.assert_not_called()

    def test_run_year_skips_optional_germany_modules_when_workspace_disables_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2025"
            paths = YearPaths.for_workspace(root, workspace_root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {
                            "germany": {"enabled": True, "filing_posture": "single"},
                            "usa": {"enabled": False, "filing_posture": "single"},
                        },
                        "investment_defaults": {
                            "crypto_supported": False,
                        },
                    }
                )
            )
            paths.manual_overrides_path.write_text(
                json.dumps(
                    {
                        "equity_comp": {
                            "include_capital_sales": False,
                        }
                    }
                )
            )

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths),
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold"),
                mock.patch("tax_pipeline.run_year.write_manifest"),
                mock.patch("tax_pipeline.run_year.extract_all_facts"),
                mock.patch("tax_pipeline.run_year.analysis_inputs_directory", return_value=paths.analysis_root),
                mock.patch("tax_pipeline.run_year.remove_obsolete_analysis_outputs"),
                mock.patch("tax_pipeline.run_year._run_pipeline_module") as mock_module_runner,
                mock.patch("tax_pipeline.run_year.ensure_required_paths"),
                mock.patch("tax_pipeline.run_year.render_germany_forms"),
                mock.patch("tax_pipeline.run_year.render_usa_forms"),
                mock.patch("tax_pipeline.run_year.render_germany_legal_audit"),
                mock.patch("tax_pipeline.run_year.render_usa_legal_audit"),
                mock.patch("tax_pipeline.run_year.print_headline_summary"),
                # F4 (W1.B / T2.1) carryforward auto-export — pipeline-shape
                # tests mock the post-pipeline export the same way they
                # already mock ``print_headline_summary``.
                mock.patch("tax_pipeline.run_year.load_final_legal_output_2025"),
                mock.patch("tax_pipeline.run_year.export_carryforwards_2025", return_value={"germany": {"path": None, "rows": 0}, "usa": {"path": None, "rows": 0}}),
            ):
                run_year(root, "2025")

            called_modules = [call.args[0] for call in mock_module_runner.call_args_list]
            self.assertNotIn("tax_pipeline.pipelines.y2025.coinbase_private_sales", called_modules)
            self.assertNotIn("tax_pipeline.pipelines.y2025.dher_german", called_modules)
            self.assertIn("tax_pipeline.pipelines.y2025.germany_model", called_modules)
            self.assertIn("tax_pipeline.pipelines.y2025.germany_elster_entry_sheet", called_modules)

    def test_run_year_rejects_unsupported_numeric_year_before_scaffolding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_workspace(root, root / "external" / "2026", 2026)

            with (
                mock.patch("tax_pipeline.run_year.resolve_year_paths", return_value=paths) as mock_resolve,
                mock.patch("tax_pipeline.run_year.ensure_year_scaffold") as mock_scaffold,
            ):
                with self.assertRaisesRegex(NotImplementedError, "Only 2025"):
                    run_year(root, "2026")

            mock_resolve.assert_called_once_with(root, "2026", workspace_root=None)
            mock_scaffold.assert_not_called()


class ScaffoldYearTest(unittest.TestCase):
    def test_scaffold_year_defaults_to_external_home_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_home = root / "home"
            fake_home.mkdir()

            with (
                mock.patch("tax_pipeline.scaffold_year.Path.home", return_value=fake_home),
                mock.patch("tax_pipeline.scaffold_year.scaffold_year") as mock_scaffold,
            ):
                scaffold_year_main(["2026"])

            project_root = Path(__file__).resolve().parents[2]
            mock_scaffold.assert_called_once_with(
                project_root,
                "2026",
                workspace_root=(fake_home / "taxes" / "2026").resolve(),
                input_fn=input,
            )

    def test_scaffold_year_uses_explicit_workspace_override(self) -> None:
        workspace_root = Path("/tmp/example-scaffold")

        with mock.patch("tax_pipeline.scaffold_year.scaffold_year") as mock_scaffold:
            scaffold_year_main(["2026", "--workspace", str(workspace_root)])

        project_root = Path(__file__).resolve().parents[2]
        mock_scaffold.assert_called_once_with(
            project_root,
            "2026",
            workspace_root=workspace_root,
            input_fn=input,
        )

    def test_scaffold_year_prompts_before_creating_missing_external_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2026"

            created_paths: list[Path] = []

            def fake_ensure(paths, **_kwargs):
                created_paths.append(paths.workspace_root)
                paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.scaffold_year.ensure_year_scaffold", side_effect=fake_ensure),
                mock.patch("tax_pipeline.scaffold_year.write_manifest"),
            ):
                run_scaffold_year(root, "2026", workspace_root=workspace_root, input_fn=lambda _prompt: "y")

            self.assertEqual(created_paths, [workspace_root.resolve()])
            self.assertTrue(workspace_root.resolve().exists())

    def test_scaffold_year_prints_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_root = root / "external" / "2026"

            stdout = io.StringIO()
            with (
                mock.patch("tax_pipeline.scaffold_year.ensure_year_scaffold") as mock_ensure,
                mock.patch("tax_pipeline.scaffold_year.write_manifest"),
                redirect_stdout(stdout),
            ):
                run_scaffold_year(root, "2026", workspace_root=workspace_root, input_fn=lambda _prompt: "y")

            output = stdout.getvalue()
            self.assertTrue(mock_ensure.called)
            self.assertIn("Workspace scaffolded at", output)
            self.assertIn("python3 -m tax_pipeline.validate_workspace 2026", output)
            self.assertIn("python3 -m tax_pipeline.run_year 2026", output)

    def test_ensure_year_scaffold_creates_profile_and_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)

            ensure_year_scaffold(paths)

            profile = json.loads(paths.profile_path.read_text())
            overrides = json.loads(paths.manual_overrides_path.read_text())
            people_csv = paths.people_path.read_text()
            payments_csv = paths.payments_path.read_text()
            elections_csv = paths.elections_path.read_text()
            manual_facts_readme = (paths.manual_facts_root / "README.md").read_text()
            reference_data_readme = (paths.reference_data_root / "README.md").read_text()
            derived_facts_readme = (paths.derived_facts_root / "README.md").read_text()
            config_readme = (paths.config_root / "README.md").read_text()
            tax_positions_readme = (paths.tax_positions_root / "README.md").read_text()

            self.assertEqual(profile["profile"], "us_person_in_berlin")
            self.assertEqual(profile["employment_city"], "Berlin")
            self.assertEqual(profile["investment_defaults"]["primary_broker_country"], "US")
            self.assertTrue(profile["investment_defaults"]["real_estate_supported"])
            self.assertEqual(profile["german_return"]["person_slots"][0]["slot"], "person_1")
            self.assertEqual(len(profile["german_return"]["person_slots"]), 1)
            self.assertEqual(profile["jurisdictions"]["germany"]["filing_posture"], "single")
            self.assertEqual(profile["jurisdictions"]["usa"]["filing_posture"], "single")
            self.assertIn("treaty_resourcing", overrides)
            self.assertIn("fund_classification", overrides)
            self.assertIn("person_id,display_name,first_name,last_name,gender,relationship_role", people_csv)
            self.assertIn("jurisdiction,person_id,payment_type,amount,currency,source,note", payments_csv)
            self.assertIn("jurisdiction,key,value,source,note", elections_csv)
            self.assertIn("reviewed fact overrides", manual_facts_readme)
            self.assertIn("ECB exchange rates", reference_data_readme)
            self.assertIn("sale lot matching", derived_facts_readme)
            self.assertIn("people.csv", config_readme)
            self.assertIn("tax-layer results", tax_positions_readme)
            self.assertTrue((paths.raw_root / "real_estate").is_dir())

    def test_ensure_year_scaffold_preserves_existing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            profile_path = paths.profile_path
            profile_path.write_text(json.dumps({"profile": "custom"}))

            ensure_year_scaffold(paths)

            self.assertEqual(json.loads(profile_path.read_text()), {"profile": "custom"})
            self.assertTrue(paths.people_path.exists())
            self.assertTrue(paths.payments_path.exists())
            self.assertTrue(paths.elections_path.exists())

    def test_ensure_year_scaffold_prompts_for_missing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)

            answers = iter(
                [
                    "Alex Example",
                    "Jordan Example",
                    "married",
                    "joint",
                    "mfs",
                    "DE",
                    "Berlin",
                    "DE",
                    "y",
                    "accrued",
                    "y",
                ]
            )

            ensure_year_scaffold(paths, prompt_if_config_missing=True, input_fn=lambda _prompt: next(answers))

            profile = json.loads(paths.profile_path.read_text())
            overrides = json.loads(paths.manual_overrides_path.read_text())
            people_csv = paths.people_path.read_text()
            elections_csv = paths.elections_path.read_text()

            self.assertEqual(profile["taxpayer"]["name"], "Alex Example")
            self.assertEqual(profile["spouse"]["name"], "Jordan Example")
            self.assertEqual(profile["german_return"]["person_slots"][0]["display_name"], "Alex Example")
            self.assertEqual(profile["german_return"]["person_slots"][1]["display_name"], "Jordan Example")
            self.assertEqual(profile["household"]["marital_status_on_dec_31"], "married")
            self.assertEqual(profile["household"]["germany_filing_status"], "joint")
            self.assertEqual(profile["household"]["us_filing_status"], "mfs")
            self.assertEqual(profile["elections"]["us_ftc_method"], "accrued")
            self.assertTrue(profile["elections"]["use_treaty_resourcing"])
            self.assertIn("fund_classification", overrides)
            self.assertIn("person_1,Alex Example,Alex,Example", people_csv)
            self.assertIn("person_2,Jordan Example,Jordan,Example", people_csv)
            self.assertIn("usa,use_treaty_resourcing,true", elections_csv)

    def test_ensure_year_scaffold_syncs_profile_from_people_and_elections_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            paths.profile_path.write_text(json.dumps({"profile": "custom", "german_return": {}, "taxpayer": {}, "spouse": {}, "household": {}, "elections": {}, "us_return": {}}))
            paths.people_path.write_text(
                "\n".join(
                    [
                        "person_id,display_name,first_name,last_name,gender,relationship_role,elster_order,us_filer,is_taxpayer,is_spouse,date_of_birth,citizenship,country_of_tax_residence,german_tax_id,us_ssn_or_itin,nra_for_us_return,german_health_insurer,german_statutory_health_with_sick_pay,german_other_vorsorge_cap_eur,church_tax_applicable",
                        "person_1,Taylor Taxpayer,Taylor,Taxpayer,,taxpayer,1,true,true,false,,US,DE,,,false,,,1900.00,",
                        "person_2,Riley Spouse,Riley,Spouse,,spouse,2,false,false,true,,,DE,,,true,,,1900.00,",
                    ]
                )
                + "\n"
            )
            paths.elections_path.write_text(
                "\n".join(
                    [
                        "jurisdiction,key,value,source,note",
                        "household,marital_status_on_dec_31,married,config,",
                        "germany,filing_status,joint,config,",
                        "germany,assume_joint_assessment_if_married,true,config,",
                        "usa,filing_status,mfs,config,",
                        "usa,default_filing_status_if_spouse_is_nonresident_alien,MFS,config,",
                        "usa,us_ftc_method,accrued,config,",
                        "usa,use_treaty_resourcing,true,config,",
                    ]
                )
                + "\n"
            )

            ensure_year_scaffold(paths)

            profile = json.loads(paths.profile_path.read_text())
            self.assertEqual(profile["taxpayer"]["name"], "Taylor Taxpayer")
            self.assertEqual(profile["spouse"]["name"], "Riley Spouse")
            self.assertEqual(profile["spouse"]["us_tax_status"], "nra")
            self.assertEqual(profile["primary_tax_residence"], "DE")
            self.assertEqual(profile["household"]["marital_status_on_dec_31"], "married")
            self.assertEqual(profile["household"]["germany_filing_status"], "joint")
            self.assertEqual(profile["household"]["us_filing_status"], "mfs")
            self.assertTrue(profile["german_return"]["assume_joint_assessment_if_married"])
            self.assertNotIn("joint_assessment_prerequisites", profile["german_return"])
            self.assertEqual(profile["us_return"]["default_filing_status_if_spouse_is_nonresident_alien"], "MFS")
            self.assertEqual(profile["elections"]["us_ftc_method"], "accrued")
            self.assertTrue(profile["elections"]["use_treaty_resourcing"])

    def test_ensure_year_scaffold_syncs_single_person_and_explicit_jurisdiction_postures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "profile": "custom",
                        "german_return": {},
                        "taxpayer": {},
                        "spouse": {},
                        "household": {},
                        "elections": {},
                        "us_return": {},
                        "jurisdictions": {},
                    }
                )
            )
            paths.people_path.write_text(
                "\n".join(
                    [
                        "person_id,display_name,first_name,last_name,gender,relationship_role,elster_order,us_filer,is_taxpayer,is_spouse,date_of_birth,citizenship,country_of_tax_residence,german_tax_id,us_ssn_or_itin,nra_for_us_return,german_health_insurer,german_statutory_health_with_sick_pay,german_other_vorsorge_cap_eur,church_tax_applicable",
                        "person_1,Taylor Taxpayer,Taylor,Taxpayer,,taxpayer,1,true,true,false,,US,DE,,,false,TK,true,1900.00,false",
                    ]
                )
                + "\n"
            )
            paths.elections_path.write_text(
                "\n".join(
                    [
                        "jurisdiction,key,value,source,note",
                        "household,marital_status_on_dec_31,single,config,",
                        "germany,enabled,true,config,",
                        "germany,filing_posture,single,config,",
                        "usa,enabled,false,config,",
                        "usa,filing_posture,single,config,",
                        "usa,us_ftc_method,accrued,config,",
                        "usa,use_treaty_resourcing,false,config,",
                    ]
                )
                + "\n"
            )

            ensure_year_scaffold(paths)

            profile = json.loads(paths.profile_path.read_text())
            self.assertEqual(profile["taxpayer"]["name"], "Taylor Taxpayer")
            self.assertEqual(profile["primary_tax_residence"], "DE")
            self.assertEqual(profile["household"]["marital_status_on_dec_31"], "single")
            self.assertEqual(len(profile["german_return"]["person_slots"]), 1)
            self.assertEqual(profile["german_return"]["person_slots"][0]["slot"], "person_1")
            self.assertEqual(profile["jurisdictions"]["germany"]["filing_posture"], "single")
            self.assertTrue(profile["jurisdictions"]["germany"]["enabled"])
            self.assertEqual(profile["jurisdictions"]["usa"]["filing_posture"], "single")
            self.assertFalse(profile["jurisdictions"]["usa"]["enabled"])

    def test_ensure_year_scaffold_preserves_custom_person_slot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "profile": "custom",
                        "german_return": {
                            "person_slots": [
                                {
                                    "slot": "person_1",
                                    "order_label": "Person 1",
                                    "display_name": "Alex Example",
                                    "owner": None,
                                    "anlage_n_label": "Anlage N (Person 1)",
                                    "anlage_kap_label": "Anlage KAP - Person 1",
                                    "kap_lines": ["17", "19"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Use the synthetic demo capital package.",
                                    "kap_notes": ["Synthetic public demo only."],
                                }
                            ]
                        },
                        "taxpayer": {},
                        "spouse": {},
                        "household": {},
                        "elections": {},
                        "us_return": {},
                        "jurisdictions": {},
                    }
                )
            )
            paths.people_path.write_text(
                "\n".join(
                    [
                        "person_id,display_name,first_name,last_name,gender,relationship_role,elster_order,us_filer,is_taxpayer,is_spouse,date_of_birth,citizenship,country_of_tax_residence,german_tax_id,us_ssn_or_itin,nra_for_us_return,german_health_insurer,german_statutory_health_with_sick_pay,german_other_vorsorge_cap_eur,church_tax_applicable",
                        "person_1,Alex Example,Alex,Example,,taxpayer,1,true,true,false,,US,DE,,,false,TK,true,1900.00,false",
                    ]
                )
                + "\n"
            )
            paths.elections_path.write_text(
                "\n".join(
                    [
                        "jurisdiction,key,value,source,note",
                        "household,marital_status_on_dec_31,single,config,",
                        "germany,enabled,true,config,",
                        "germany,filing_posture,single,config,",
                        "usa,enabled,true,config,",
                        "usa,filing_posture,single,config,",
                    ]
                )
                + "\n"
            )

            ensure_year_scaffold(paths)

            profile = json.loads(paths.profile_path.read_text())
            slot = profile["german_return"]["person_slots"][0]
            self.assertEqual(slot["kap_posture"], "Use the synthetic demo capital package.")
            self.assertEqual(slot["kap_notes"], ["Synthetic public demo only."])


if __name__ == "__main__":
    unittest.main()
