from __future__ import annotations

import json
import unittest

from tax_pipeline.pipelines.y2025.final_legal_output import write_final_legal_output_2025
from tests.generated_demo import generated_demo_paths


class FinalLegalOutputTest(unittest.TestCase):
    def test_enabled_jurisdiction_missing_required_artifact_fails_closed(self) -> None:
        with generated_demo_paths() as paths:
            missing = paths.analysis_root / "germany-n-work-expenses.csv"
            missing.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "germany-n-work-expenses.csv"):
                write_final_legal_output_2025(paths)

    def test_disabled_jurisdiction_missing_artifacts_are_explicitly_not_applicable(self) -> None:
        with generated_demo_paths() as paths:
            profile = json.loads(paths.profile_path.read_text())
            profile["jurisdictions"]["usa"]["enabled"] = False
            paths.profile_path.write_text(json.dumps(profile))
            (paths.analysis_root / "us-tax-estimate.json").unlink()
            (paths.analysis_root / "us-capital-results.json").unlink()
            (paths.analysis_root / "us-treaty-package.json").unlink()

            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        self.assertEqual(output["usa"]["forms"]["status"], "not_applicable")
        self.assertEqual(output["usa"]["legal_audit"]["status"], "not_applicable")

    def test_present_empty_bucket_csv_fails_when_core_has_reportable_us_capital_rows(self) -> None:
        with generated_demo_paths() as paths:
            (paths.analysis_root / "us-form-8949-income-buckets.csv").write_text(
                "form,line_or_bucket,amount_usd,note\n"
            )

            with self.assertRaisesRegex(FileNotFoundError, "us-form-8949-income-buckets.csv"):
                write_final_legal_output_2025(paths)

    def test_malformed_csv_extra_columns_fail_closed(self) -> None:
        # Final legal output is the renderer boundary. A malformed CSV row with
        # overflow cells must fail closed instead of silently dropping data before
        # the law/template cross-check can see it.
        with generated_demo_paths() as paths:
            (paths.analysis_root / "germany-model-trace.csv").write_text("step,value_eur\nbase,1,unexpected\n")

            with self.assertRaisesRegex(ValueError, "Malformed CSV row.*germany-model-trace.csv.*extra column"):
                write_final_legal_output_2025(paths)

    def test_us_final_output_rejects_tax_and_treaty_package_payment_mismatch(self) -> None:
        # Renderers consume final-legal-output.json only. The final-output builder
        # must therefore verify that the U.S. model result and treaty package agree
        # before exposing Form 1040 line 35a/37 values.
        with generated_demo_paths() as paths:
            treaty_path = paths.analysis_root / "us-treaty-package.json"
            treaty = json.loads(treaty_path.read_text())
            treaty["form_1040"]["line_35a_refund_usd"] = "999.99"
            treaty_path.write_text(json.dumps(treaty))

            with self.assertRaisesRegex(ValueError, "U.S. final output mismatch.*line_35a_refund_usd"):
                write_final_legal_output_2025(paths)

    def test_us_final_output_derives_refund_split_from_signed_result_not_cached_split_fields(self) -> None:
        # Form 1040 lines 35a/37 are the positive/negative split of the signed
        # core payment result. Cached split fields in us-tax-estimate.json must not
        # become an alternate source of truth if they drift from that signed amount.
        with generated_demo_paths() as paths:
            estimate_path = paths.analysis_root / "us-tax-estimate.json"
            estimate = json.loads(estimate_path.read_text())
            estimate["payments"]["refund_with_treaty_resourcing_usd"] = "999.99"
            estimate["payments"]["amount_owed_with_treaty_resourcing_usd"] = "0.00"
            estimate_path.write_text(json.dumps(estimate))

            treaty_path = paths.analysis_root / "us-treaty-package.json"
            treaty = json.loads(treaty_path.read_text())
            treaty["form_1040"]["line_35a_refund_usd"] = "999.99"
            treaty["form_1040"]["line_37_amount_owed_usd"] = "0.00"
            treaty_path.write_text(json.dumps(treaty))

            with self.assertRaisesRegex(ValueError, "U.S. final output mismatch.*refund_with_treaty_resourcing_usd"):
                write_final_legal_output_2025(paths)

    def test_germany_married_separate_final_output_fails_closed_until_section_26a_is_modeled(self) -> None:
        # § 26a EStG separate assessment needs separate spouse-linked outputs and
        # allocation handling. The public final-output boundary must not publish a
        # household aggregate under a married_separate posture until that model exists.
        with generated_demo_paths() as paths:
            results_path = paths.analysis_root / "germany-model-results.json"
            results = json.loads(results_path.read_text())
            results["ordinary"]["filing_posture"] = "married_separate"
            results_path.write_text(json.dumps(results))

            with self.assertRaisesRegex(NotImplementedError, "married_separate"):
                write_final_legal_output_2025(paths)

    def test_final_output_rejects_blank_trace_legal_references_and_authorities(self) -> None:
        # The final legal output is the renderer boundary. Trace rows without a
        # legal reference or authority URL cannot support code-vs-law audit.
        with generated_demo_paths() as paths:
            germany_trace = paths.analysis_root / "germany-model-trace.csv"
            germany_trace.write_text(
                germany_trace.read_text().replace(
                    "§ 19 Abs. 1 EStG,https://www.gesetze-im-internet.de/estg/__19.html",
                    ",https://www.gesetze-im-internet.de/estg/__19.html",
                    1,
                )
            )

            with self.assertRaisesRegex(ValueError, "germany-model-trace.csv.*legal_reference"):
                write_final_legal_output_2025(paths)

        with generated_demo_paths() as paths:
            us_trace = paths.analysis_root / "us-tax-trace.csv"
            us_trace.write_text(
                us_trace.read_text().replace(
                    "https://www.irs.gov/individuals/international-taxpayers/yearly-average-currency-exchange-rates",
                    "",
                    1,
                )
            )

            with self.assertRaisesRegex(ValueError, "us-tax-trace.csv.*authority_url"):
                write_final_legal_output_2025(paths)

    def test_us_final_output_rejects_form_1040_projection_mismatch_before_rendering(self) -> None:
        # Form 1040 line projections are rendered from final-legal-output.json.
        # The final-output builder must catch stale treaty package lines, not just
        # final refund/amount-owed drift.
        with generated_demo_paths() as paths:
            treaty_path = paths.analysis_root / "us-treaty-package.json"
            treaty = json.loads(treaty_path.read_text())
            treaty["form_1040"]["line_20_schedule_3_usd"] = "999.99"
            treaty_path.write_text(json.dumps(treaty))

            with self.assertRaisesRegex(ValueError, "U.S. final output mismatch.*line_20_schedule_3_usd"):
                write_final_legal_output_2025(paths)

    def test_us_final_output_rejects_capital_results_sidecar_drift_from_tax_estimate(self) -> None:
        # U.S. renderers receive only final-legal-output.json. Therefore the final
        # output builder must reject a stale us-capital-results.json sidecar before
        # it can disagree with the 26 U.S.C. §§ 1211/1212 capital result in the core.
        with generated_demo_paths() as paths:
            capital_path = paths.analysis_root / "us-capital-results.json"
            capital_results = json.loads(capital_path.read_text())
            capital_results["capital"]["short_box_a_usd"] = "999.99"
            capital_path.write_text(json.dumps(capital_results))

            with self.assertRaisesRegex(ValueError, "U.S. final output mismatch.*us-capital-results.json.*short_box_a_usd"):
                write_final_legal_output_2025(paths)

    def test_us_final_output_rejects_form_8949_bucket_drift_from_tax_estimate(self) -> None:
        # Form 8949 bucket rows are allowed as a CSV-shaped projection only if they
        # match the core Schedule D / Form 8949 values carried in us-tax-estimate.json.
        with generated_demo_paths() as paths:
            buckets_path = paths.analysis_root / "us-form-8949-income-buckets.csv"
            buckets_path.write_text(
                buckets_path.read_text().replace(
                    "Form 8949,Part I Box A,350.00",
                    "Form 8949,Part I Box A,999.99",
                    1,
                )
            )

            with self.assertRaisesRegex(ValueError, "U.S. final output mismatch.*us-form-8949-income-buckets.csv.*Part I Box A"):
                write_final_legal_output_2025(paths)

    def test_germany_final_output_rejects_anlage_n_work_expense_drift_from_core_projection(self) -> None:
        # Anlage N rows are final-output projections of the Germany core model.
        # A hand-edited work-expense CSV must not silently change the form package.
        with generated_demo_paths() as paths:
            n_path = paths.analysis_root / "germany-n-work-expenses.csv"
            n_path.write_text(
                n_path.read_text().replace(
                    "Anlage N (Person 1),58,Homeoffice days without first workplace visit,0,",
                    "Anlage N (Person 1),58,Homeoffice days without first workplace visit,99,",
                    1,
                )
            )

            with self.assertRaisesRegex(ValueError, "Germany final output mismatch.*germany-n-work-expenses.csv"):
                write_final_legal_output_2025(paths)

    def test_germany_final_output_requires_core_anlage_n_entry_projection(self) -> None:
        # Germany Anlage N rendering must consume the typed core render projection.
        # The final-output boundary may validate sidecar CSVs, but it must not
        # reconstruct filing entries by reopening extracted facts or raw support files.
        with generated_demo_paths() as paths:
            results_path = paths.analysis_root / "germany-model-results.json"
            results = json.loads(results_path.read_text())
            results.setdefault("render_projection", {}).setdefault("elster", {}).pop(
                "anlage_n_entries_by_slot",
                None,
            )
            results_path.write_text(json.dumps(results))

            with self.assertRaisesRegex(FileNotFoundError, "render_projection.elster.anlage_n_entries_by_slot"):
                write_final_legal_output_2025(paths)

    def test_germany_final_output_rejects_elster_entry_sheet_drift_from_core_projection(self) -> None:
        # The ELSTER narrative sheet is still distributed as output text, but it
        # must be the core render_projection text. A stale markdown file cannot
        # become an alternate source of filing instructions.
        with generated_demo_paths() as paths:
            (paths.analysis_root / "germany-elster-entry-sheet.md").write_text("# stale entry sheet\n")

            with self.assertRaisesRegex(ValueError, "Germany final output mismatch.*germany-elster-entry-sheet.md"):
                write_final_legal_output_2025(paths)

    def test_germany_final_output_rejects_kap_csv_drift_from_core_projection(self) -> None:
        # The Germany renderer consumes KAP rows from final-legal-output.json. Those
        # rows must be byte-for-byte projections of the core § 20 / § 32d output,
        # not independently edited sidecar CSV values.
        with generated_demo_paths() as paths:
            kap_path = paths.analysis_root / "germany-kap-summary.csv"
            kap_path.write_text(kap_path.read_text().replace("Anlage KAP - Person 1,20,1500.00", "Anlage KAP - Person 1,20,9999.00", 1))

            with self.assertRaisesRegex(ValueError, "Germany final output mismatch.*germany-kap-summary.csv"):
                write_final_legal_output_2025(paths)

    def test_germany_final_output_rejects_kap_inv_fund_csv_drift_from_core_projection(self) -> None:
        # InvStG § 20 fund classifications and amounts are bucket-sensitive. The
        # final-output boundary must reject stale per-fund KAP-INV support rows.
        with generated_demo_paths() as paths:
            kap_inv_path = paths.analysis_root / "germany-kap-inv-fund-summary.csv"
            kap_inv_path.write_text(kap_inv_path.read_text().replace("VTI,aktienfonds,120.00", "VTI,aktienfonds,999.99", 1))

            with self.assertRaisesRegex(ValueError, "Germany final output mismatch.*germany-kap-inv-fund-summary.csv"):
                write_final_legal_output_2025(paths)

    def test_final_output_writes_durable_legal_execution_graph_artifacts(self) -> None:
        # The self-audit surface must include the exact rule graph used to render
        # narratives so law order can be checked independently of Markdown prose.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            graph_path = paths.analysis_root / "legal-execution-graph.json"
            mermaid_path = paths.analysis_root / "legal-execution-graph.mmd"

            output = json.loads(output_path.read_text())
            graph = json.loads(graph_path.read_text())
            mermaid = mermaid_path.read_text()

        self.assertEqual(graph["schema_version"], 1)
        self.assertGreaterEqual(len(graph["nodes"]), 20)
        node_by_rule = {node["rule_id"]: node for node in graph["nodes"]}
        self.assertIn("DE25-08-INCOME-TAX-TARIFF", node_by_rule)
        self.assertIn("US25-18-TREATY-ADDITIONAL-FTC", node_by_rule)
        self.assertTrue(node_by_rule["US25-18-TREATY-ADDITIONAL-FTC"]["output_fingerprints"])
        self.assertTrue(all(node["template_id"] == node["rule_id"] for node in graph["nodes"]))
        self.assertIn("US25-18-TREATY-ADDITIONAL-FTC", mermaid)

        packets_by_node = {}
        for country, languages in output["narratives"].items():
            for language, packets in languages.items():
                for packet in packets:
                    packets_by_node[f"{country}-{language}-{packet['rule_id']}"] = packet
        for node in graph["nodes"]:
            self.assertEqual(
                node["audit_packet_fingerprint"],
                packets_by_node[node["node_id"]]["fingerprint"],
            )

    def test_legal_execution_graph_rejects_template_ids_that_do_not_match_rule_ids(self) -> None:
        # The graph is the durable audit contract. It must not accept a narrative
        # packet whose prose template can drift away from the executed rule node.
        from tax_pipeline.pipelines.y2025.final_legal_output import build_legal_execution_graph_2025

        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        output["narratives"]["US"]["en"][0]["template_id"] = "US25-OTHER-TEMPLATE"

        with self.assertRaisesRegex(ValueError, "template_id to equal rule_id"):
            build_legal_execution_graph_2025(output)


if __name__ == "__main__":
    unittest.main()
