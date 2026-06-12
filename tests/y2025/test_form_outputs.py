from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.forms import (
    FormEntry,
    markdown_heading,
    markdown_link,
    markdown_table,
    render_germany_forms,
    render_usa_forms,
    required_germany_form_paths,
    required_usa_form_paths,
    write_form,
)
from tax_pipeline.legal_audit import (
    render_germany_legal_audit,
    render_usa_legal_audit,
    required_germany_legal_audit_paths,
    required_usa_legal_audit_paths,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import write_final_legal_output_2025
from tests.generated_demo import populate_demo_workspace


def _render_germany_forms_from_final(paths: YearPaths) -> None:
    if paths.profile_path.exists():
        profile = json.loads(paths.profile_path.read_text())
        profile.setdefault("jurisdictions", {}).setdefault("usa", {})["enabled"] = False
        paths.profile_path.write_text(json.dumps(profile))
    germany_trace = paths.analysis_root / "germany-model-trace.csv"
    if not germany_trace.exists():
        germany_trace.write_text(
            "step,value_eur,note,legal_reference,authority_url\n"
            "synthetic_form_fixture,0.00,form-only fixture,§ 2 EStG,https://www.gesetze-im-internet.de/estg/__2.html\n"
        )
    germany_audit = paths.analysis_root / "germany-audit-note.md"
    if not germany_audit.exists():
        germany_audit.write_text("# Germany Legal Audit\n\nForm-only fixture.\n")
    germany_assumptions = paths.tax_positions_root / "de-model-assumptions.csv"
    if not germany_assumptions.exists():
        germany_assumptions.write_text("section,key,value,source,note\n")
    results_path = paths.analysis_root / "germany-model-results.json"
    if results_path.exists():
        profile = json.loads(paths.profile_path.read_text()) if paths.profile_path.exists() else {}
        default_posture = (
            profile.get("jurisdictions", {}).get("germany", {}).get("filing_posture")
            or profile.get("household", {}).get("germany_filing_status")
            or "single"
        )
        results = json.loads(results_path.read_text())
        ordinary = results.setdefault("ordinary", {})
        ordinary.setdefault("filing_posture", default_posture)
        ordinary.setdefault("joint_taxable_income_eur", "0.00")
        ordinary.setdefault("joint_income_tax_eur", "0.00")
        # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage Vorsorgeaufwand
        # bucket scalars produced by DE25-05 / DE25-06. Synthetic form
        # fixtures default to zero-amount rows so the form-line surface
        # is auditable on the synthetic posture (per CLAUDE.md
        # fail-closed posture for missing rule outputs).
        ordinary.setdefault("vorsorge_retirement_total_eur", "0.00")
        ordinary.setdefault("vorsorge_basic_health_eur", "0.00")
        ordinary.setdefault("vorsorge_other_allowed_eur", "0.00")
        # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage Sonderausgaben
        # bucket scalars (DE25-SPENDENABZUG, DE25-UNTERHALTSLEISTUNGEN,
        # DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG). Synthetic form fixtures
        # default to zero so the form-line surface is auditable on the
        # synthetic posture.
        ordinary.setdefault("sonderausgaben_spenden_eur", "0.00")
        ordinary.setdefault("sonderausgaben_unterhalt_eur", "0.00")
        ordinary.setdefault("sonderausgaben_pauschbetrag_eur", "0.00")
        # FREELANCER-DE-EUER-SLICE-SPEC.md sub-slice 3: § 18 EStG selbständige
        # Arbeit net profit (§ 4 Abs. 3 EStG EÜR Gewinn) produced by DE25-EUER
        # (de.ordinary.business_profit_eur). Synthetic form fixtures are wage
        # earners with no self-employment → a legitimate explicit zero so the
        # Anlage S Freiberufler-Gewinn line is auditable on the no-business
        # posture. https://www.gesetze-im-internet.de/estg/__18.html
        ordinary.setdefault("business_profit_eur", "0.00")
        # C5 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage Kind extension —
        # § 32 Abs. 6 EStG Kinderfreibetrag/BEA household total +
        # § 31 EStG Günstigerprüfung counterfactual saving + Kindergeld
        # received audit cross-check + qualifying-children count.
        # Synthetic form fixtures default to zero-amount rows + zero
        # qualifying children so the form-line surface is auditable on
        # the no-children posture (CLAUDE.md fail-closed).
        children_block = results.setdefault("children", {})
        children_block.setdefault("qualifying_children_count", 0)
        children_block.setdefault("kinderfreibetrag_total_eur", "0.00")
        children_block.setdefault("kinderfreibetrag_tax_saving_eur", "0.00")
        children_block.setdefault("kindergeld_total_eur", "0.00")
        children_block.setdefault("disability_pauschbetrag_transferred_eur", "0.00")
        children_block.setdefault("guenstigerpruefung_choice", "kindergeld")
        children_block.setdefault("applied_relief_eur", "0.00")
        capital = results.setdefault("capital", {})
        capital.setdefault("stock_gain_eur", "0.00")
        capital.setdefault("fund_gain_eur", "0.00")
        capital.setdefault("explicit_foreign_tax_total_eur", "0.00")
        capital.setdefault("net_creditable_foreign_tax_total_eur", "0.00")
        capital.setdefault("foreign_tax_credit_cap_eur", "0.00")
        capital.setdefault("foreign_tax_credit_applied_eur", "0.00")
        capital.setdefault("capital_income_tax_with_teilfreistellung_eur", "0.00")
        capital.setdefault("capital_income_tax_after_foreign_credit_eur", "0.00")
        capital.setdefault("capital_tax_with_teilfreistellung_after_treaty_eur", "0.00")
        render_projection = results.setdefault("render_projection", {}).setdefault("elster", {})
        if "kap_summary_rows" not in render_projection:
            kap_rows = list(csv.DictReader((paths.analysis_root / "germany-kap-summary.csv").read_text().splitlines()))
            render_projection["kap_summary_rows"] = [
                [row["form"], row["line"], row["amount_eur"], row["note"]]
                for row in kap_rows
            ]
        if "kap_inv_fund_rows" not in render_projection:
            kap_inv_path = paths.analysis_root / "germany-kap-inv-fund-summary.csv"
            kap_inv_rows = list(csv.DictReader(kap_inv_path.read_text().splitlines())) if kap_inv_path.exists() else []
            render_projection["kap_inv_fund_rows"] = [
                [row["symbol"], row["fund_type"], row["income_eur"], row["sale_result_eur"], row["combined_eur"]]
                for row in kap_inv_rows
            ]
        # Anlage Kind 2025 — § 33b Abs. 5 EStG transferred Pauschbetrag
        # surface for the form-renderer. Synthetic form fixtures default
        # to a single zero-amount Zeile 65 row so the form-line surface
        # is auditable on the synthetic posture (no qualifying child) per
        # invariant I3. https://www.gesetze-im-internet.de/estg/__33b.html
        if "kind_summary_rows" not in render_projection:
            kind_path = paths.analysis_root / "germany-kind-summary.csv"
            if kind_path.exists():
                kind_csv_rows = list(
                    csv.DictReader(kind_path.read_text().splitlines())
                )
                render_projection["kind_summary_rows"] = [
                    [row["form"], row["line"], row["amount_eur"], row["note"]]
                    for row in kind_csv_rows
                ]
            else:
                kind_row = [
                    "Anlage Kind",
                    "65",
                    "0.00",
                    "Synthetic form fixture (no qualifying child has a "
                    "§ 33b Abs. 3 EStG Pauschbetrag).",
                ]
                render_projection["kind_summary_rows"] = [kind_row]
                import io as _io
                _kind_buf = _io.StringIO()
                _kind_writer = csv.writer(_kind_buf, lineterminator="\n")
                _kind_writer.writerow(["form", "line", "amount_eur", "note"])
                _kind_writer.writerow(kind_row)
                kind_path.write_text(_kind_buf.getvalue(), encoding="utf-8")
        if "n_breakdown_rows" not in render_projection:
            n_path = paths.analysis_root / "germany-n-work-expenses.csv"
            n_rows = list(csv.DictReader(n_path.read_text().splitlines())) if n_path.exists() else []
            render_projection["n_breakdown_rows"] = [
                [row["form"], row["line"], row["description"], row["amount_eur"], row["note"]]
                for row in n_rows
            ]
        if "entry_sheet_markdown" not in render_projection:
            entry_path = paths.analysis_root / "germany-elster-entry-sheet.md"
            render_projection["entry_sheet_markdown"] = entry_path.read_text() if entry_path.exists() else ""
        if "anlage_n_entries_by_slot" not in render_projection:
            person_slots = profile.get("german_return", {}).get("person_slots", [])
            fact_docs = [
                json.loads(path.read_text())
                for path in paths.facts_root.glob("*.facts.json")
                if path.exists()
            ]

            def wage_entry(slot: dict, label: str, key: str) -> dict[str, str]:
                owner = slot.get("owner")
                facts = [
                    fact
                    for doc in fact_docs
                    if doc.get("doc_type") == "german_lohnsteuer_pdf" and doc.get("owner") == owner
                    for fact in doc.get("facts", [])
                    if fact.get("key") == key
                ]
                amount = sum((Decimal(str(fact.get("value", "0.00"))) for fact in facts), Decimal("0.00"))
                sources = "; ".join(sorted({str(fact.get("source", {}).get("file", "")) for fact in facts if fact.get("source")}))
                return {
                    "label": label,
                    "value": f"{amount:.2f} EUR",
                    "source": sources or "germany-model-results.json",
                    "notes": "Synthetic form-test projection.",
                }

            render_projection["anlage_n_entries_by_slot"] = {}
            n_rows = render_projection.get("n_breakdown_rows", [])
            for slot in person_slots:
                form_name = slot["anlage_n_label"]
                # A3 (FORM-MAPPING-FOLLOWUP): test-fixture labels mirror the
                # production ``anlage_n_entries_projection_2025`` change —
                # rows now name the destination Anlage N Zeile (Z6 / Z7 /
                # Z8 / Z16) instead of the source Lohnsteuerbescheinigung
                # eDaten Zeile (Z3 / Z4 / Z5 / Z10). The eDaten Zeile is
                # carried in the row notes for traceability.
                entries = [
                    wage_entry(slot, "Anlage N Zeile 6 (Bruttoarbeitslohn)", "gross_wage_eur"),
                    wage_entry(slot, "Anlage N Zeile 7 (Einbehaltene Lohnsteuer)", "withheld_wage_tax_eur"),
                    wage_entry(slot, "Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag)", "withheld_solidarity_surcharge_eur"),
                    wage_entry(slot, "Anlage N Zeile 16 (Mehrjährige Bezüge)", "multiannual_wage_eur"),
                ]
                person_n_rows = [row for row in n_rows if row[0] == form_name]
                for row in person_n_rows:
                    if row[1] == "61-64":
                        continue
                    value = f"{row[3]} days" if row[1] in {"58", "59"} else f"{Decimal(str(row[3])):.2f} EUR"
                    entries.append(
                        {
                            "label": f"Anlage N Zeile {row[1]}" if row[1] not in {"54-56", "61-64"} else f"Anlage N Zeilen {row[1]}",
                            "value": value,
                            "source": "germany-n-work-expenses.csv",
                            "notes": row[4],
                        }
                    )
                other_rows = [row for row in person_n_rows if row[1] == "61-64"]
                if other_rows:
                    entries.append(
                        {
                            "label": "Anlage N Zeilen 61-64",
                            "value": f"{sum((Decimal(str(row[3])) for row in other_rows), Decimal('0.00')):.2f} EUR",
                            "source": "germany-n-work-expenses.csv",
                            "notes": "Aggregated from the structured 61-64 rows in `germany-n-work-expenses.csv`.",
                        }
                    )
                render_projection["anlage_n_entries_by_slot"][slot["slot"]] = entries
        results_path.write_text(json.dumps(results))
    # Test-isolation defect (flagged Group A audit + Group C executor): the
    # full ``write_final_legal_output_2025`` pipeline calls
    # ``build_rule_narratives_2025``, which fails closed when the Germany
    # ordinary rule-graph execution is missing from pipeline_context. The
    # synthetic form-renderer fixtures in this module never run the rule
    # graph (they exercise rendering only), so within this helper we stub
    # narratives to an empty dict. When the suite runs in order the prior
    # tests happen to populate context, masking the defect; running these
    # tests in isolation surfaces it. The stub is local to the form-
    # renderer helper and does NOT affect production pipelines (run_year /
    # populate_demo_workspace), which still build narratives from the
    # real executed graph.
    with mock.patch(
        "tax_pipeline.pipelines.y2025.final_legal_output.build_rule_narratives_2025",
        return_value={},
    ):
        write_final_legal_output_2025(paths)
    render_germany_forms(paths)


def _render_usa_forms_from_final(paths: YearPaths) -> None:
    with mock.patch(
        "tax_pipeline.pipelines.y2025.final_legal_output.build_rule_narratives_2025",
        return_value={},
    ):
        write_final_legal_output_2025(paths)
    render_usa_forms(paths)


def _render_germany_legal_audit_from_final(paths: YearPaths) -> None:
    with mock.patch(
        "tax_pipeline.pipelines.y2025.final_legal_output.build_rule_narratives_2025",
        return_value={},
    ):
        write_final_legal_output_2025(paths)
    render_germany_legal_audit(paths)


def _render_usa_legal_audit_from_final(paths: YearPaths) -> None:
    with mock.patch(
        "tax_pipeline.pipelines.y2025.final_legal_output.build_rule_narratives_2025",
        return_value={},
    ):
        write_final_legal_output_2025(paths)
    render_usa_legal_audit(paths)


class TestFormHelpers(unittest.TestCase):
    def test_renderers_require_only_final_legal_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = YearPaths.for_year(Path(tmp), 2025)
            final_output = paths.analysis_root / "final-legal-output.json"

            self.assertEqual(required_germany_form_paths(paths), [final_output])
            self.assertEqual(required_usa_form_paths(paths), [final_output])
            self.assertEqual(required_germany_legal_audit_paths(paths), [final_output])
            self.assertEqual(required_usa_legal_audit_paths(paths), [final_output])

    def test_markdown_helpers_and_form_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "years" / "2025" / "outputs" / "forms" / "germany" / "sample.md"

            self.assertEqual(markdown_heading("2025 Anlage KAP", level=2), "## 2025 Anlage KAP")
            self.assertEqual(markdown_heading("2025 <script>", level=2), "## 2025 &lt;script&gt;")
            self.assertEqual(markdown_link("index.md", "index.md"), "[index.md](index.md)")
            self.assertEqual(
                markdown_table(
                    ("Line", "Value"),
                    [("Anlage KAP Zeile 19", "4839.22 EUR"), ("<b>user</b>|line", "<script>")],
                ),
                "\n".join(
                    [
                        "| Line | Value |",
                        "| --- | --- |",
                        "| Anlage KAP Zeile 19 | 4839.22 EUR |",
                        "| &lt;b&gt;user&lt;/b&gt;\\|line | &lt;script&gt; |",
                    ]
                ),
            )

            content = write_form(
                path,
                "2025 Sample Form",
                ["Posture line"],
                [FormEntry("Anlage KAP Zeile 19", "4839.22 EUR", source="sample.csv", notes="sample note")],
                ["Source note"],
            )

            self.assertTrue(path.exists())
            self.assertIn("# 2025 Sample Form", content)
            self.assertIn("## Posture", content)
            self.assertIn("| Anlage KAP Zeile 19 | 4839.22 EUR | sample.csv | sample note |", content)
            self.assertIn("## Notes", content)

    def test_render_germany_forms_supports_single_person_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {
                            "germany": {"enabled": True, "filing_posture": "single"},
                        },
                        "german_return": {
                            "person_slots": [
                                {
                                    "slot": "person_1",
                                    "order_label": "Person 1",
                                    "display_name": "Taylor Taxpayer",
                                    "owner": "person_1",
                                    "anlage_n_label": "Anlage N (Person 1)",
                                    "anlage_kap_label": "Anlage KAP - Person 1",
                                    "kap_lines": ["17", "19", "20", "23", "41"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Use person 1's foreign-capital package.",
                                    "kap_notes": [],
                                }
                            ]
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-model-results.json").write_text(
                json.dumps(
                    {
                        "ordinary": {"filing_posture": "single"},
                        "refunds": {
                            "final_target_refund_eur": "100.00",
                            "other_income_22nr3_eur": "0.00",
                            "equipment_work_share_total_eur": "0.00",
                        },
                        "capital": {
                            "capital_tax_with_teilfreistellung_after_treaty_eur": "0.00",
                            "dher_stock_gain_eur": "0.00",
                        },
                        "private_sales": {
                            "private_sale_result_eur": "0.00",
                        },
                        "vanilla_checkpoint": {
                            "taxable_income_eur": "1000.00",
                            "income_tax_eur": "0.00",
                            "soli_eur": "0.00",
                            "total_tax_eur": "0.00",
                            "refund_or_balance_due_eur": "100.00",
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-summary.md").write_text("- Chosen filing target refund: 100.00 EUR\n")
            (paths.analysis_root / "germany-elster-entry-sheet.md").write_text("single filer audit\n")
            (paths.analysis_root / "germany-kap-summary.csv").write_text(
                "\n".join(
                    [
                        "form,line,amount_eur,note",
                        "Anlage KAP - Person 1,4,1000.00,Sparer-Pauschbetrag claim (§ 20 Abs. 9 Satz 1 EStG).",
                        "Anlage KAP - Person 1,17,0.00,none",
                        "Anlage KAP - Person 1,19,10.00,none",
                        "Anlage KAP - Person 1,20,0.00,none",
                        "Anlage KAP - Person 1,21,0.00,none",
                        "Anlage KAP - Person 1,23,0.00,none",
                        "Anlage KAP - Person 1,24,0.00,none",
                        "Anlage KAP - Person 1,41,0.00,none",
                        "Anlage KAP-INV,4,0.00,none",
                        "Anlage KAP-INV,8,0.00,none",
                        "Anlage KAP-INV,9-13,0.00,none",
                        "Anlage KAP-INV,14,0.00,none",
                        "Anlage KAP-INV,26,0.00,none",
                    ]
                )
                + "\n"
            )
            (paths.analysis_root / "germany-n-work-expenses.csv").write_text(
                "form,line,description,amount_eur,note\n"
            )
            (paths.analysis_root / "germany-kap-inv-fund-summary.csv").write_text(
                "symbol,fund_type,income_eur,sale_result_eur,combined_eur\n"
            )
            (paths.facts_root / "single-wage.facts.json").write_text(
                json.dumps(
                    {
                        "doc_type": "german_lohnsteuer_pdf",
                        "owner": "person_1",
                        "relative_path": "germany/single-wage.pdf",
                        "facts": [
                            {"key": "gross_wage_eur", "value": "60000.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                            {"key": "withheld_wage_tax_eur", "value": "12000.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                            {"key": "withheld_solidarity_surcharge_eur", "value": "0.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                            {"key": "multiannual_wage_eur", "value": "0.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                        ],
                    }
                )
            )

            _render_germany_forms_from_final(paths)

            self.assertTrue((paths.germany_forms_root / "2025_anlage_n_person_1.md").exists())
            self.assertTrue((paths.germany_forms_root / "2025_anlage_kap_person_1.md").exists())
            self.assertFalse((paths.germany_forms_root / "2025_anlage_n_person_2.md").exists())
            self.assertFalse((paths.germany_forms_root / "2025_anlage_kap_person_2.md").exists())
            haupt_text = (paths.germany_forms_root / "2025_hauptvordruck.md").read_text()
            index_text = (paths.germany_forms_root / "index.md").read_text()
            # C6 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Mantelbogen
            # identity row carries the German Veranlagungsart label
            # rather than the legacy English-prose summary.
            self.assertIn("Hauptvordruck (Identifikation)", haupt_text)
            self.assertIn("Einzelveranlagung (single)", haupt_text)
            self.assertNotIn("2025_anlage_n_person_2.md", index_text)

    def test_render_germany_forms_rejects_married_separate_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {
                            "germany": {"enabled": True, "filing_posture": "married_separate"},
                        },
                        "german_return": {
                            "person_slots": [
                                {
                                    "slot": "person_1",
                                    "order_label": "Person 1",
                                    "display_name": "Taylor Taxpayer",
                                    "owner": "person_1",
                                    "anlage_n_label": "Anlage N (Person 1)",
                                    "anlage_kap_label": "Anlage KAP - Person 1",
                                    "kap_lines": ["17", "19", "20", "23", "41"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Use person 1's capital package.",
                                    "kap_notes": [],
                                },
                                {
                                    "slot": "person_2",
                                    "order_label": "Person 2",
                                    "display_name": "Morgan Taxpayer",
                                    "owner": "person_2",
                                    "anlage_n_label": "Anlage N (Person 2)",
                                    "anlage_kap_label": "Anlage KAP - Person 2",
                                    "kap_lines": ["7", "8", "17", "37", "38", "40", "41"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Use person 2's certificate amounts.",
                                    "kap_notes": [],
                                },
                            ]
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-model-results.json").write_text(
                json.dumps(
                    {
                        "ordinary": {"filing_posture": "married_separate"},
                        "refunds": {
                            "final_target_refund_eur": "150.00",
                            "other_income_22nr3_eur": "0.00",
                            "equipment_work_share_total_eur": "0.00",
                        },
                        "capital": {
                            "capital_tax_with_teilfreistellung_after_treaty_eur": "0.00",
                            "dher_stock_gain_eur": "0.00",
                        },
                        "private_sales": {
                            "private_sale_result_eur": "0.00",
                        },
                        "vanilla_checkpoint": {
                            "taxable_income_eur": "2000.00",
                            "income_tax_eur": "0.00",
                            "soli_eur": "0.00",
                            "total_tax_eur": "0.00",
                            "refund_or_balance_due_eur": "150.00",
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-summary.md").write_text("- Chosen filing target refund: 150.00 EUR\n")
            (paths.analysis_root / "germany-elster-entry-sheet.md").write_text("married separate audit\n")
            (paths.analysis_root / "germany-kap-summary.csv").write_text(
                "\n".join(
                    [
                        "form,line,amount_eur,note",
                        "Anlage KAP - Person 1,4,1000.00,Sparer-Pauschbetrag claim (§ 20 Abs. 9 Satz 1 EStG).",
                        "Anlage KAP - Person 1,17,0.00,none",
                        "Anlage KAP - Person 1,19,10.00,none",
                        "Anlage KAP - Person 1,20,0.00,none",
                        "Anlage KAP - Person 1,21,0.00,none",
                        "Anlage KAP - Person 1,23,0.00,none",
                        "Anlage KAP - Person 1,24,0.00,none",
                        "Anlage KAP - Person 1,41,0.00,none",
                        "Anlage KAP - Person 2,4,1000.00,Sparer-Pauschbetrag claim (§ 20 Abs. 9 Satz 1 EStG).",
                        "Anlage KAP - Person 2,7,5.00,none",
                        "Anlage KAP - Person 2,8,0.00,none",
                        "Anlage KAP - Person 2,17,0.00,none",
                        "Anlage KAP - Person 2,37,0.00,none",
                        "Anlage KAP - Person 2,38,0.00,none",
                        "Anlage KAP - Person 2,40,0.00,none",
                        "Anlage KAP - Person 2,41,0.00,none",
                        "Anlage KAP-INV,4,0.00,none",
                        "Anlage KAP-INV,8,0.00,none",
                        "Anlage KAP-INV,9-13,0.00,none",
                        "Anlage KAP-INV,14,0.00,none",
                        "Anlage KAP-INV,26,0.00,none",
                    ]
                )
                + "\n"
            )
            (paths.analysis_root / "germany-n-work-expenses.csv").write_text(
                "form,line,description,amount_eur,note\n"
            )
            (paths.analysis_root / "germany-kap-inv-fund-summary.csv").write_text(
                "symbol,fund_type,income_eur,sale_result_eur,combined_eur\n"
            )
            (paths.facts_root / "wage-1.facts.json").write_text(
                json.dumps(
                    {
                        "doc_type": "german_lohnsteuer_pdf",
                        "owner": "person_1",
                        "relative_path": "germany/wage-1.pdf",
                        "facts": [
                            {"key": "gross_wage_eur", "value": "60000.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                            {"key": "withheld_wage_tax_eur", "value": "12000.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                            {"key": "withheld_solidarity_surcharge_eur", "value": "0.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                            {"key": "multiannual_wage_eur", "value": "0.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                        ],
                    }
                )
            )
            (paths.facts_root / "wage-2.facts.json").write_text(
                json.dumps(
                    {
                        "doc_type": "german_lohnsteuer_pdf",
                        "owner": "person_2",
                        "relative_path": "germany/wage-2.pdf",
                        "facts": [
                            {"key": "gross_wage_eur", "value": "30000.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                            {"key": "withheld_wage_tax_eur", "value": "3000.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                            {"key": "withheld_solidarity_surcharge_eur", "value": "0.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                            {"key": "multiannual_wage_eur", "value": "0.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                        ],
                    }
                )
            )

            with self.assertRaisesRegex(
                NotImplementedError,
                "married_separate.*not supported",
            ):
                _render_germany_forms_from_final(paths)

    def test_render_germany_forms_consults_posture_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {
                            "germany": {"enabled": True, "filing_posture": "single"},
                        },
                        "german_return": {
                            "person_slots": [
                                {
                                    "slot": "person_1",
                                    "order_label": "Person 1",
                                    "display_name": "Taylor Taxpayer",
                                    "owner": "person_1",
                                    "anlage_n_label": "Anlage N (Person 1)",
                                    "anlage_kap_label": "Anlage KAP - Person 1",
                                    "kap_lines": ["17", "19", "20", "23", "41"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Use person 1's foreign-capital package.",
                                    "kap_notes": [],
                                }
                            ]
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-model-results.json").write_text(
                json.dumps(
                    {
                        "ordinary": {"filing_posture": "single"},
                        "refunds": {
                            "final_target_refund_eur": "100.00",
                            "other_income_22nr3_eur": "0.00",
                            "equipment_work_share_total_eur": "0.00",
                        },
                        "capital": {
                            "capital_tax_with_teilfreistellung_after_treaty_eur": "0.00",
                            "dher_stock_gain_eur": "0.00",
                        },
                        "private_sales": {"private_sale_result_eur": "0.00"},
                        "vanilla_checkpoint": {
                            "taxable_income_eur": "1000.00",
                            "income_tax_eur": "0.00",
                            "soli_eur": "0.00",
                            "total_tax_eur": "0.00",
                            "refund_or_balance_due_eur": "100.00",
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-summary.md").write_text("- Chosen filing target refund: 100.00 EUR\n")
            (paths.analysis_root / "germany-elster-entry-sheet.md").write_text("single filer audit\n")
            (paths.analysis_root / "germany-kap-summary.csv").write_text(
                "\n".join(
                    [
                        "form,line,amount_eur,note",
                        "Anlage KAP - Person 1,4,1000.00,Sparer-Pauschbetrag claim (§ 20 Abs. 9 Satz 1 EStG).",
                        "Anlage KAP - Person 1,17,0.00,none",
                        "Anlage KAP - Person 1,19,10.00,none",
                        "Anlage KAP - Person 1,20,0.00,none",
                        "Anlage KAP - Person 1,21,0.00,none",
                        "Anlage KAP - Person 1,23,0.00,none",
                        "Anlage KAP - Person 1,24,0.00,none",
                        "Anlage KAP - Person 1,41,0.00,none",
                        "Anlage KAP-INV,4,0.00,none",
                        "Anlage KAP-INV,8,0.00,none",
                        "Anlage KAP-INV,9-13,0.00,none",
                        "Anlage KAP-INV,14,0.00,none",
                        "Anlage KAP-INV,26,0.00,none",
                    ]
                )
                + "\n"
            )
            (paths.analysis_root / "germany-n-work-expenses.csv").write_text("form,line,description,amount_eur,note\n")
            (paths.analysis_root / "germany-kap-inv-fund-summary.csv").write_text(
                "symbol,fund_type,income_eur,sale_result_eur,combined_eur\n"
            )
            (paths.facts_root / "single-wage.facts.json").write_text(
                json.dumps(
                    {
                        "doc_type": "german_lohnsteuer_pdf",
                        "owner": "person_1",
                        "relative_path": "germany/single-wage.pdf",
                        "facts": [
                            {"key": "gross_wage_eur", "value": "60000.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                            {"key": "withheld_wage_tax_eur", "value": "12000.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                            {"key": "withheld_solidarity_surcharge_eur", "value": "0.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                            {"key": "multiannual_wage_eur", "value": "0.00", "source": {"file": "germany/single-wage.pdf"}, "notes": ""},
                        ],
                    }
                )
            )

            with mock.patch("tax_pipeline.forms.germany.get_posture_definition", create=True) as mocked:
                _render_germany_forms_from_final(paths)

            mocked.assert_called_once_with("germany", "single")


class TestGermanyForms(unittest.TestCase):
    def _seed_germany_analysis_outputs(self, paths: YearPaths) -> None:
        materialized = populate_demo_workspace(paths.project_root, year=paths.year)
        self.assertEqual(materialized.year_root, paths.year_root)

    def test_render_germany_forms_writes_country_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_analysis_outputs(paths)
            (paths.germany_forms_root / "2025_anlage_n_person_1_legacy.md").write_text("stale")
            (paths.germany_forms_root / "2025_anlage_kap_person_2_legacy.md").write_text("stale")

            _render_germany_forms_from_final(paths)

            expected_files = [
                paths.germany_forms_root / "index.md",
                paths.germany_forms_root / "2025_hauptvordruck.md",
                paths.germany_forms_root / "2025_anlage_n_person_1.md",
                paths.germany_forms_root / "2025_anlage_kap_person_1.md",
                paths.germany_forms_root / "2025_anlage_kap_inv.md",
                paths.germany_forms_root / "2025_anlage_so.md",
                paths.germany_forms_root / "2025_anlage_s.md",
            ]
            for path in expected_files:
                self.assertTrue(path.exists(), path)
            self.assertFalse((paths.germany_forms_root / "2025_anlage_n_person_1_legacy.md").exists())
            self.assertFalse((paths.germany_forms_root / "2025_anlage_kap_person_2_legacy.md").exists())

            source_results = json.loads((paths.analysis_root / "germany-model-results.json").read_text())
            germany_result = Decimal(source_results["refunds"]["final_target_refund_eur"])
            germany_result_phrase = (
                f"{abs(germany_result).quantize(Decimal('0.01'))} EUR balance due"
                if germany_result < Decimal("0.00")
                else f"{germany_result.quantize(Decimal('0.01'))} EUR refund"
            )
            index_text = (paths.germany_forms_root / "index.md").read_text()
            haupt_text = (paths.germany_forms_root / "2025_hauptvordruck.md").read_text()
            kap_person_1_text = (paths.germany_forms_root / "2025_anlage_kap_person_1.md").read_text()
            kap_inv_text = (paths.germany_forms_root / "2025_anlage_kap_inv.md").read_text()
            n_person_1_text = (paths.germany_forms_root / "2025_anlage_n_person_1.md").read_text()
            so_text = (paths.germany_forms_root / "2025_anlage_so.md").read_text()
            anlage_s_text = (paths.germany_forms_root / "2025_anlage_s.md").read_text()

            self.assertIn(
                f"Final modeled result: **{germany_result_phrase}**.",
                index_text,
            )
            self.assertIn(
                "Reflect the audited entry sheet and saved model outputs.",
                haupt_text,
            )
            # C6 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Mantelbogen
            # identity row carries the German Veranlagungsart label
            # rather than the legacy English-prose summary.
            self.assertIn(
                "| Hauptvordruck (Identifikation) | Einzelveranlagung (single) | config/profile.json |  |",
                haupt_text,
            )
            self.assertIn(
                "| Prepayment note | See audit note | germany-elster-entry-sheet.md | The prepayment is not transmitted as a filing line. |",
                haupt_text,
            )
            self.assertIn("Filing posture: `single`", index_text)
            self.assertNotIn("2025_anlage_n_person_2.md", index_text)
            self.assertNotIn("2025_anlage_kap_person_2.md", index_text)
            self.assertIn("| Anlage KAP Zeile 19 | 1780.00 EUR |", kap_person_1_text)
            self.assertIn("| Anlage KAP-INV Zeile 4 | 120.00 EUR |", kap_inv_text)
            # A3 (FORM-MAPPING-FOLLOWUP): assertions track the destination
            # Anlage N Zeile labels (Z6 / Z7 / Z8 / Z16) the production
            # projection now emits. The synthetic test fixture's
            # ``wage_entry`` helper above only fills label / value /
            # source / notes (the notes are the literal "Synthetic
            # form-test projection." rather than the citation-rich
            # production strings), so the matchers below test the bare
            # destination-Zeile labels. No legal math changed.
            # A3 (FORM-MAPPING-FOLLOWUP): production projection notes name
            # the source Lohnsteuerbescheinigung Zeile + cite the
            # statutory authority. We assert label + value + source +
            # the leading "Source: Lohnsteuerbescheinigung Zeile <N>"
            # token of the notes column (the rest of the note carries
            # the § citation and is exercised by the projection unit
            # tests directly).
            self.assertIn("| Anlage N Zeile 6 (Bruttoarbeitslohn) | 120000.00 EUR | germany/alex-north-lohnsteuer-2025.pdf | Source: Lohnsteuerbescheinigung Zeile 3.", n_person_1_text)
            self.assertIn("| Anlage N Zeile 7 (Einbehaltene Lohnsteuer) | 28000.00 EUR | germany/alex-north-lohnsteuer-2025.pdf | Source: Lohnsteuerbescheinigung Zeile 4.", n_person_1_text)
            self.assertIn("| Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag) | 1540.00 EUR | germany/alex-north-lohnsteuer-2025.pdf | Source: Lohnsteuerbescheinigung Zeile 5.", n_person_1_text)
            self.assertIn("| Anlage N Zeile 16 (Mehrjährige Bezüge) | 0.00 EUR | germany/alex-north-lohnsteuer-2025.pdf | Source: Lohnsteuerbescheinigung Zeile 10.", n_person_1_text)
            self.assertNotIn("| Anlage N Zeilen 54-56 |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 58 | 0 days |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 59 | 0 days |", n_person_1_text)
            self.assertNotIn("retained in `germany-elster-entry-sheet.md`", n_person_1_text)
            self.assertIn("| Anlage SO Zeilen 14-21 | 0.00 EUR |", so_text)
            self.assertIn("| Anlage SO Zeilen 41-47 | 0.00 EUR | germany-model-results.json | Current documented private-sale result (Coinbase crypto bucket) from the saved model; § 23 EStG private Veräußerungsgeschäfte at virtuelle Währungen / sonstige Token. |", so_text)
            self.assertIn("| Anlage SO Zeile 62 |  | germany-elster-entry-sheet.md | Prior-year carryforward handling remains in the audit entry sheet. |", so_text)
            # FREELANCER-DE-EUER-SLICE-SPEC.md sub-slice 3: the demo is a wage
            # earner with no § 18 EStG selbständige Arbeit → the § 4 Abs. 3
            # EÜR Gewinn (DE25-EUER → de.ordinary.business_profit_eur) is a
            # legitimate 0.00, rendered (not blank) on the Anlage S
            # Freiberufler-Gewinn line. https://www.gesetze-im-internet.de/estg/__18.html
            self.assertIn("| Anlage S Zeile 4 | 0.00 EUR | germany-model-results.json | § 18 EStG Gewinn aus freiberuflicher Tätigkeit (§ 4 Abs. 3 EStG EÜR: Betriebseinnahmen − Betriebsausgaben) from stage DE25-EUER. |", anlage_s_text)

    def test_anlage_s_renders_section_18_profit_for_self_employed(self) -> None:
        # FREELANCER-DE-EUER-SLICE-SPEC.md sub-slice 3 + § 9 numeric gate.
        # § 18 EStG selbständige Arbeit, § 4 Abs. 3 EStG EÜR:
        #   Gewinn = Betriebseinnahmen − Betriebsausgaben
        #          = 80,000.00 − 18,250.00 = 61,750.00.
        # https://www.gesetze-im-internet.de/estg/__18.html
        # https://www.gesetze-im-internet.de/estg/__4.html
        from tax_pipeline.forms.germany import _write_anlage_s

        with tempfile.TemporaryDirectory() as tmp:
            paths = YearPaths.for_year(Path(tmp), 2025)
            paths.ensure_directories()
            results = {"ordinary": {"business_profit_eur": "61750.00"}}
            # Provenance carrying the DE25-EUER StageResult fingerprint for
            # the form-line scalar — exercises the I11 stage-backed path
            # (not the synthetic-fingerprint fallback).
            provenance = {
                "form_lines": {
                    "DE": {
                        "de.ordinary.business_profit_eur": {
                            "stage_id": "DE25-EUER",
                            "output_key": "de.ordinary.business_profit_eur",
                            "fingerprint": "euer-fingerprint-deadbeef",
                        }
                    }
                }
            }
            _write_anlage_s(paths, results, provenance)
            text = (paths.germany_forms_root / "2025_anlage_s.md").read_text()
            self.assertIn(
                "| Anlage S Zeile 4 | 61750.00 EUR | germany-model-results.json | "
                "§ 18 EStG Gewinn aus freiberuflicher Tätigkeit (§ 4 Abs. 3 EStG "
                "EÜR: Betriebseinnahmen − Betriebsausgaben) from stage DE25-EUER. |",
                text,
            )

    def test_anlage_s_renders_zero_for_wage_earner_not_blank(self) -> None:
        # § 2 Abs. 1 Nr. 3 EStG: a wage earner has no selbständige Arbeit, so
        # the § 18 / § 4 Abs. 3 Gewinn is a legitimate explicit zero and must
        # render as 0.00 (not blank) per the null/zero/missing contract.
        # https://www.gesetze-im-internet.de/estg/__18.html
        from tax_pipeline.forms.germany import _write_anlage_s

        with tempfile.TemporaryDirectory() as tmp:
            paths = YearPaths.for_year(Path(tmp), 2025)
            paths.ensure_directories()
            results = {"ordinary": {"business_profit_eur": "0.00"}}
            _write_anlage_s(paths, results, None)
            text = (paths.germany_forms_root / "2025_anlage_s.md").read_text()
            self.assertIn("| Anlage S Zeile 4 | 0.00 EUR |", text)

    def test_render_germany_anlage_n_uses_projected_final_output_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_analysis_outputs(paths)

            final_path = write_final_legal_output_2025(paths)
            final_output = json.loads(final_path.read_text())
            forms = final_output["germany"]["forms"]
            self.assertIn("anlage_n_entries_by_slot", forms)
            self.assertIn("person_1", forms["anlage_n_entries_by_slot"])

            forms.pop("fact_documents", None)
            forms.pop("n_work_expense_rows", None)
            final_path.write_text(json.dumps(final_output))
            (paths.analysis_root / "germany-n-work-expenses.csv").unlink()
            for fact_path in paths.facts_root.glob("*.facts.json"):
                fact_path.unlink()

            render_germany_forms(paths)

            n_person_1_text = (paths.germany_forms_root / "2025_anlage_n_person_1.md").read_text()
            # A3 (FORM-MAPPING-FOLLOWUP): destination Anlage N Zeile labels.
            self.assertIn("| Anlage N Zeile 6 (Bruttoarbeitslohn) | 120000.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 7 (Einbehaltene Lohnsteuer) | 28000.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag) | 1540.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 16 (Mehrjährige Bezüge) | 0.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 58 | 0 days | germany-n-work-expenses.csv |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 59 | 0 days | germany-n-work-expenses.csv |", n_person_1_text)

    def test_render_germany_anlage_n_fails_closed_when_projected_entries_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_analysis_outputs(paths)

            final_path = write_final_legal_output_2025(paths)
            final_output = json.loads(final_path.read_text())
            final_output["germany"]["forms"]["anlage_n_entries_by_slot"].pop("person_1")
            final_path.write_text(json.dumps(final_output))

            with self.assertRaisesRegex(
                FileNotFoundError,
                "Missing Germany final legal output field: anlage_n_entries_by_slot.person_1",
            ):
                render_germany_forms(paths)

    def test_seeded_germany_entry_sheet_includes_pre_submit_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_analysis_outputs(paths)

            entry_text = (paths.analysis_root / "germany-elster-entry-sheet.md").read_text()

            self.assertIn("## Pre-Submit Checklist", entry_text)
            self.assertIn("`1500.00 EUR` prepayment", entry_text)
            self.assertIn("`88.29 EUR balance due`", entry_text)
            self.assertIn("Do not enter every individual fund trade into ELSTER", entry_text)

    def test_render_germany_forms_scopes_deductions_by_person_and_renders_person_2_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            paths.profile_path.write_text(
                json.dumps(
                    {
                        "jurisdictions": {"germany": {"enabled": True, "filing_posture": "married_joint"}},
                        "german_return": {
                            "person_slots": [
                                {
                                    "slot": "person_1",
                                    "order_label": "Person 1",
                                    "display_name": "Taylor Taxpayer",
                                    "owner": "person_1",
                                    "anlage_n_label": "Anlage N (Person 1)",
                                    "anlage_kap_label": "Anlage KAP - Person 1",
                                    "kap_lines": ["17", "19", "20", "23", "41"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Synthetic person 1 capital package.",
                                    "kap_notes": [],
                                },
                                {
                                    "slot": "person_2",
                                    "order_label": "Person 2",
                                    "display_name": "Morgan Taxpayer",
                                    "owner": "person_2",
                                    "anlage_n_label": "Anlage N (Person 2)",
                                    "anlage_kap_label": "Anlage KAP - Person 2",
                                    "kap_lines": ["7", "8", "17", "37", "38", "40", "41"],
                                    "kap_raw_lines": [],
                                    "kap_posture": "Synthetic person 2 certificate path.",
                                    "kap_notes": [],
                                },
                            ]
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-model-results.json").write_text(
                json.dumps(
                    {
                        "ordinary": {"filing_posture": "married_joint"},
                        "refunds": {
                            "final_target_refund_eur": "150.00",
                            "other_income_22nr3_eur": "0.00",
                            "equipment_work_share_total_eur": "75.00",
                        },
                        "capital": {
                            "capital_tax_with_teilfreistellung_after_treaty_eur": "0.00",
                            "dher_stock_gain_eur": "0.00",
                            "domestic_capital_withholding_credit_eur": "33.21",
                        },
                        "private_sales": {"private_sale_result_eur": "0.00"},
                        "vanilla_checkpoint": {
                            "taxable_income_eur": "2000.00",
                            "income_tax_eur": "0.00",
                            "soli_eur": "0.00",
                            "total_tax_eur": "0.00",
                            "refund_or_balance_due_eur": "150.00",
                        },
                    }
                )
            )
            (paths.analysis_root / "germany-summary.md").write_text("- Chosen filing target refund: 150.00 EUR\n")
            (paths.analysis_root / "germany-elster-entry-sheet.md").write_text("joint synthetic audit\n")
            (paths.analysis_root / "germany-kap-summary.csv").write_text(
                "form,line,amount_eur,note\n"
                "Anlage KAP - Person 1,4,1000.00,Sparer-Pauschbetrag claim (§ 20 Abs. 9 Satz 1 EStG).\n"
                "Anlage KAP - Person 1,17,0.00,none\n"
                "Anlage KAP - Person 1,19,10.00,none\n"
                "Anlage KAP - Person 1,20,0.00,none\n"
                "Anlage KAP - Person 1,21,0.00,none\n"
                "Anlage KAP - Person 1,23,0.00,none\n"
                "Anlage KAP - Person 1,24,0.00,none\n"
                "Anlage KAP - Person 1,41,0.00,none\n"
                "Anlage KAP - Person 2,4,1000.00,Sparer-Pauschbetrag claim (§ 20 Abs. 9 Satz 1 EStG).\n"
                "Anlage KAP - Person 2,7,5.00,none\n"
                "Anlage KAP - Person 2,8,0.00,none\n"
                "Anlage KAP - Person 2,17,0.00,none\n"
                "Anlage KAP - Person 2,37,0.00,none\n"
                "Anlage KAP - Person 2,38,0.00,none\n"
                "Anlage KAP - Person 2,40,0.00,none\n"
                "Anlage KAP - Person 2,41,0.00,none\n"
                "Anlage KAP-INV,4,0.00,none\n"
                "Anlage KAP-INV,8,0.00,none\n"
                "Anlage KAP-INV,9-13,0.00,none\n"
                "Anlage KAP-INV,14,0.00,none\n"
                "Anlage KAP-INV,26,0.00,none\n"
            )
            (paths.analysis_root / "germany-n-work-expenses.csv").write_text(
                "form,line,description,amount_eur,note\n"
                "Anlage N (Person 1),54-56,Person 1 Arbeitsmittel,142.20,Person 1 work materials.\n"
                "Anlage N (Person 1),58,Person 1 Homeoffice ohne erste Tätigkeitsstätte,156,Person 1 homeoffice days.\n"
                "Anlage N (Person 1),59,Person 1 Homeoffice mit erster Tätigkeitsstätte,0,Person 1 visit days.\n"
                "Anlage N (Person 1),61-64,Person 1 Telefon / Internet,1938.14,Person 1 telecom deduction.\n"
                "Anlage N (Person 2),54-56,Person 2 Arbeitsmittel,50.00,Person 2 work materials.\n"
                "Anlage N (Person 2),58,Person 2 Homeoffice ohne erste Tätigkeitsstätte,20,Person 2 homeoffice days.\n"
                "Anlage N (Person 2),59,Person 2 Homeoffice mit erster Tätigkeitsstätte,3,Person 2 visit days.\n"
                "Anlage N (Person 2),61-64,Person 2 Telefon / Internet,25.00,Person 2 telecom deduction.\n"
            )
            (paths.analysis_root / "germany-kap-inv-fund-summary.csv").write_text(
                "symbol,fund_type,income_eur,sale_result_eur,combined_eur\n"
            )
            (paths.facts_root / "wage-1.facts.json").write_text(
                json.dumps(
                    {
                        "doc_type": "german_lohnsteuer_pdf",
                        "owner": "person_1",
                        "relative_path": "germany/wage-1.pdf",
                        "facts": [
                            {"key": "gross_wage_eur", "value": "60000.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                            {"key": "withheld_wage_tax_eur", "value": "12000.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                            {"key": "withheld_solidarity_surcharge_eur", "value": "0.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                            {"key": "multiannual_wage_eur", "value": "0.00", "source": {"file": "germany/wage-1.pdf"}, "notes": ""},
                        ],
                    }
                )
            )
            (paths.facts_root / "wage-2.facts.json").write_text(
                json.dumps(
                    {
                        "doc_type": "german_lohnsteuer_pdf",
                        "owner": "person_2",
                        "relative_path": "germany/wage-2.pdf",
                        "facts": [
                            {"key": "gross_wage_eur", "value": "30000.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                            {"key": "withheld_wage_tax_eur", "value": "3000.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                            {"key": "withheld_solidarity_surcharge_eur", "value": "0.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                            {"key": "multiannual_wage_eur", "value": "0.00", "source": {"file": "germany/wage-2.pdf"}, "notes": ""},
                        ],
                    }
                )
            )

            _render_germany_forms_from_final(paths)

            n_person_1_text = (paths.germany_forms_root / "2025_anlage_n_person_1.md").read_text()
            n_person_2_text = (paths.germany_forms_root / "2025_anlage_n_person_2.md").read_text()
            index_text = (paths.germany_forms_root / "index.md").read_text()

            self.assertIn("Domestic capital withholding credited under §36: `33.21 EUR`", index_text)
            self.assertIn("| Anlage N Zeilen 54-56 | 142.20 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 58 | 156 days |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 59 | 0 days |", n_person_1_text)
            self.assertIn("| Anlage N Zeilen 61-64 | 1938.14 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeilen 54-56 | 50.00 EUR | germany-n-work-expenses.csv | Person 2 work materials. |", n_person_2_text)
            self.assertIn("| Anlage N Zeile 58 | 20 days | germany-n-work-expenses.csv | Person 2 homeoffice days. |", n_person_2_text)
            self.assertIn("| Anlage N Zeile 59 | 3 days | germany-n-work-expenses.csv | Person 2 visit days. |", n_person_2_text)
            self.assertIn("| Anlage N Zeilen 61-64 | 25.00 EUR | germany-n-work-expenses.csv | Aggregated from the structured 61-64 rows in `germany-n-work-expenses.csv`. |", n_person_2_text)
            self.assertNotIn("No deduction rows present", n_person_2_text)

    def test_render_germany_forms_does_not_reopen_fact_documents_after_core_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_analysis_outputs(paths)

            facts_root = paths.facts_root
            original = json.loads((facts_root / "alex-north-wage.facts.json").read_text())
            second = json.loads(json.dumps(original))
            second["relative_path"] = "germany/person_1-second-employer.pdf"
            second["facts"] = [
                {
                    **fact,
                    "source": {**fact["source"], "file": "germany/person_1-second-employer.pdf"},
                }
                for fact in second["facts"]
            ]
            replacements = {
                "gross_wage_eur": "1000.00",
                "withheld_wage_tax_eur": "200.00",
                "withheld_solidarity_surcharge_eur": "10.00",
                "multiannual_wage_eur": "0.00",
            }
            for fact in second["facts"]:
                if fact["key"] in replacements:
                    fact["value"] = replacements[fact["key"]]
            (facts_root / "germany_person_1_second_employer_pdf.facts.json").write_text(json.dumps(second))

            _render_germany_forms_from_final(paths)

            n_person_1_text = (paths.germany_forms_root / "2025_anlage_n_person_1.md").read_text()
            # A3 (FORM-MAPPING-FOLLOWUP): destination Anlage N Zeile labels.
            self.assertIn("| Anlage N Zeile 6 (Bruttoarbeitslohn) | 120000.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 7 (Einbehaltene Lohnsteuer) | 28000.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag) | 1540.00 EUR |", n_person_1_text)
            self.assertIn("| Anlage N Zeile 16 (Mehrjährige Bezüge) | 0.00 EUR |", n_person_1_text)
            self.assertIn("germany/alex-north-lohnsteuer-2025.pdf", n_person_1_text)
            self.assertNotIn("germany/person_1-second-employer.pdf", n_person_1_text)

    def test_render_germany_forms_shows_balance_due_when_result_is_negative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_analysis_outputs(paths)

            results_path = paths.analysis_root / "germany-model-results.json"
            results = json.loads(results_path.read_text())
            results["refunds"]["final_target_refund_eur"] = "-10.50"
            results_path.write_text(json.dumps(results))

            _render_germany_forms_from_final(paths)

            index_text = (paths.germany_forms_root / "index.md").read_text()
            haupt_text = (paths.germany_forms_root / "2025_hauptvordruck.md").read_text()

            self.assertIn("Final modeled result: **10.50 EUR balance due**.", index_text)
            # C6 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Estimation row now
            # carries an audit-trail note explaining the Mantelbogen
            # does not transmit the refund — the Finanzamt computes it.
            self.assertIn("| Estimation | 10.50 EUR balance due | germany-model-results.json |", haupt_text)


class TestUSAForms(unittest.TestCase):
    def _seed_usa_analysis_outputs(self, paths: YearPaths) -> None:
        materialized = populate_demo_workspace(paths.project_root, year=paths.year)
        self.assertEqual(materialized.year_root, paths.year_root)

    def test_seeded_usa_entry_sheet_includes_pre_submit_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)

            entry_text = (paths.analysis_root / "us-treaty-entry-sheet.md").read_text()

            self.assertIn("## Pre-Submit Checklist", entry_text)
            self.assertIn("`1000.00 USD` estimated payment", entry_text)
            self.assertIn("`778.08 USD refund`", entry_text)
            self.assertIn("`20572.64 USD balance due`", entry_text)

    def test_render_usa_forms_writes_country_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            (paths.usa_forms_root / "old.md").write_text("stale")

            _render_usa_forms_from_final(paths)

            expected_files = [
                paths.usa_forms_root / "index.md",
                paths.usa_forms_root / "2025_1040.md",
                paths.usa_forms_root / "2025_schedule_1.md",
                paths.usa_forms_root / "2025_schedule_b.md",
                paths.usa_forms_root / "2025_schedule_d.md",
                paths.usa_forms_root / "2025_form_8949.md",
                paths.usa_forms_root / "2025_form_6781.md",
                paths.usa_forms_root / "2025_form_8960.md",
                paths.usa_forms_root / "2025_form_1116_passive.md",
                paths.usa_forms_root / "2025_form_1116_general.md",
            ]
            for path in expected_files:
                self.assertTrue(path.exists(), path)
            self.assertFalse((paths.usa_forms_root / "old.md").exists())

            index_text = (paths.usa_forms_root / "index.md").read_text()
            form_1040_text = (paths.usa_forms_root / "2025_1040.md").read_text()
            schedule_1_text = (paths.usa_forms_root / "2025_schedule_1.md").read_text()
            schedule_d_text = (paths.usa_forms_root / "2025_schedule_d.md").read_text()
            form_8949_text = (paths.usa_forms_root / "2025_form_8949.md").read_text()
            form_6781_text = (paths.usa_forms_root / "2025_form_6781.md").read_text()
            form_8960_text = (paths.usa_forms_root / "2025_form_8960.md").read_text()
            passive_text = (paths.usa_forms_root / "2025_form_1116_passive.md").read_text()
            general_text = (paths.usa_forms_root / "2025_form_1116_general.md").read_text()

            self.assertIn("Final modeled result: **778.08 USD refund**.", index_text)
            self.assertIn("| Line 35a | 778.08 USD | us-treaty-package.json | Refund amount; zero when the chosen treaty posture has a balance due. |", form_1040_text)
            self.assertIn("| Line 8z total | 0.00 USD | us-capital-results.json |  |", schedule_1_text)
            self.assertIn("| Line 8z statement - staking income | 0.00 USD | us-capital-results.json | Digital-asset staking income. |", schedule_1_text)
            self.assertIn("| Net capital result | 1050.00 USD | us-capital-results.json | Net capital result before the annual deduction cap. |", schedule_d_text)
            self.assertIn("| Capital loss carryforward to 2026 | 0.00 USD | us-capital-results.json |  |", schedule_d_text)
            self.assertIn("| Part I Box H | 0.00 USD | us-form-8949-income-buckets.csv | Short digital-asset transactions not reported with basis to the IRS |", form_8949_text)
            self.assertIn("| 40% short-term portion | 0.00 USD | us-capital-results.json |  |", form_6781_text)
            self.assertIn("| 60% long-term portion | 0.00 USD | us-capital-results.json |  |", form_6781_text)
            # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 line-level
            # decomposition. Form 1040 line 7a flows to Form 8960 line
            # 5a (capital gain/loss component of NII).
            self.assertIn("| Line 5a | 1050.00 USD | us-treaty-package.json | Net gain/loss from disposition of property (Form 1040 line 7a). |", form_8960_text)
            # B5 — Form 8960 line 17 = NIIT scalar carried to Schedule
            # 2 line 12 from the executed US25-20-NIIT rule output.
            self.assertIn("| Line 17 | 0.00 USD | us-treaty-package.json | Net Investment Income Tax — 3.8 % × min(line 12, max(0, MAGI − threshold)). Carries to Schedule 2 line 12. |", form_8960_text)
            # F-USFORM-9: Form 1116 labels prefixed with the IRS line number
            # (Line 1a / Line 8 / Line 10 / Line 21 / Line 22 / Line 32) per
            # the 2024-revision form. The 2025 form retains the same line
            # numbering as of publication. https://www.irs.gov/forms-pubs/about-form-1116
            self.assertIn("| Line 1a (foreign-source passive dividends) | 503.97 USD | usa/ftc-support.csv | Schwab page 90 documented foreign-source passive dividends. |", passive_text)
            self.assertIn("| Line 1a (foreign-source net capital gain) | 0.00 USD | usa/ftc-support.csv | No documented foreign-source net capital gain in the demo. |", passive_text)
            self.assertIn("| Line 32 / Part IV (Pub. 514 worksheet add-on) | 0.00 USD | us-treaty-package.json | Publication 514 additional foreign tax credit on U.S. income (Certain Income Resourced by Treaty basket — see § 904(d)(6)). |", passive_text)
            self.assertIn("| Line 1a (Germany wage basket income) | 135440.18 USD | us-tax-estimate.json |  |", general_text)
            self.assertIn("| Line 22 (allowed general credit) | 21607.22 USD | us-tax-estimate.json | Smaller of line 14 (foreign tax) or line 21 (limitation). |", general_text)
            schedule_b_text = (paths.usa_forms_root / "2025_schedule_b.md").read_text()
            # Schedule B Part I (Line 2) is rendered because the demo posture
            # has a foreign account, which requires Part I and III regardless
            # of the $1,500 threshold (commit fe7c685, IRS Form 1040
            # Instructions / Schedule B). Part II (Line 5) is NOT rendered for
            # the demo because ordinary dividends ($820) do not exceed the
            # $1,500 threshold; Schedule B Part II is conditional on the
            # dividend threshold only, not on the foreign-account flag. The
            # qualified-dividend reminder still appears in the Notes section.
            self.assertIn("| Line 2 | 25.00 USD | us-capital-results.json | Taxable interest (Schedule B Part I). |", schedule_b_text)
            self.assertNotIn("| Line 5 |", schedule_b_text)
            self.assertIn("Qualified dividends remain on Form 1040 line 3a, not Schedule B line 5.", schedule_b_text)

    def test_render_germany_index_ignores_poisoned_summary_text_and_uses_core_output(self) -> None:
        # Renderers consume final-legal-output.json as the already-validated legal
        # boundary. A stale/unvalidated germany-summary.md string embedded in that
        # output must not override the structured core result values.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            materialized = populate_demo_workspace(paths.project_root, year=paths.year)
            self.assertEqual(materialized.year_root, paths.year_root)
            final_path = write_final_legal_output_2025(paths)
            final_output = json.loads(final_path.read_text())
            final_output["germany"]["forms"]["summary_text"] = (
                "- Chosen filing target refund: 999999.99 EUR refund\n"
                "- Work-equipment share included: 999999.99 EUR\n"
                "- Other income included under § 22 Nr. 3: 999999.99 EUR\n"
            )
            final_path.write_text(json.dumps(final_output))

            render_germany_forms(paths)

            index_text = (paths.germany_forms_root / "index.md").read_text()

        self.assertIn("- Chosen filing target refund: -88.29 EUR", index_text)
        self.assertIn("- Work-equipment share included: 0.00 EUR", index_text)
        self.assertIn("- Other income included under § 22 Nr. 3: 0.00 EUR", index_text)
        self.assertNotIn("999999.99", index_text)

    def test_render_usa_form_1116_marks_treaty_addon_not_applicable_when_not_claimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = YearPaths.for_year(Path(tmp), 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            estimate_path = paths.analysis_root / "us-tax-estimate.json"
            estimate = json.loads(estimate_path.read_text())
            estimate["manual_positions"]["use_treaty_resourcing"] = "no"
            estimate["ftc"]["total_allowed_ftc_after_treaty_resourcing_usd"] = estimate["ftc"]["total_allowed_ftc_usd"]
            estimate["payments"]["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"] = estimate["payments"]["refund_if_positive_else_balance_due_usd"]
            estimate["payments"]["refund_with_treaty_resourcing_usd"] = estimate["payments"]["refund_without_treaty_resourcing_usd"]
            estimate["payments"]["amount_owed_with_treaty_resourcing_usd"] = estimate["payments"]["amount_owed_without_treaty_resourcing_usd"]
            estimate_path.write_text(json.dumps(estimate))

            packet_path = paths.analysis_root / "us-treaty-package.json"
            packet = json.loads(packet_path.read_text())
            packet["chosen_position"]["treaty_resourcing_claimed"] = "no"
            packet["form_1040"]["line_20_schedule_3_usd"] = estimate["ftc"]["total_allowed_ftc_usd"]
            packet["form_1040"]["line_35a_refund_usd"] = estimate["payments"]["refund_without_treaty_resourcing_usd"]
            packet["form_1040"]["line_37_amount_owed_usd"] = estimate["payments"]["amount_owed_without_treaty_resourcing_usd"]
            packet["schedule_3"]["line_1_foreign_tax_credit_usd"] = estimate["ftc"]["total_allowed_ftc_usd"]
            packet["schedule_3"]["line_8_total_nonrefundable_credits_usd"] = estimate["ftc"]["total_allowed_ftc_usd"]
            packet["treaty_resourcing_worksheet"]["status"] = "not_applicable"
            packet["treaty_resourcing_worksheet"]["line_21_additional_credit_usd"] = "0.00"
            packet_path.write_text(json.dumps(packet))

            _render_usa_forms_from_final(paths)

            passive_text = (paths.usa_forms_root / "2025_form_1116_passive.md").read_text()

        self.assertIn("| Treaty re-sourcing add-on | Not applicable | us-treaty-package.json | Treaty re-sourcing is not claimed in the selected posture. |", passive_text)
        self.assertNotIn("Publication 514 additional foreign tax credit on U.S. income", passive_text)

    def test_render_usa_schedule_d_and_form_6781_use_final_capital_model_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            write_final_legal_output_2025(paths)

            final_output_path = paths.analysis_root / "final-legal-output.json"
            final_output = json.loads(final_output_path.read_text())
            schedule_d_entries = final_output["usa"]["forms"]["schedule_d_entries"]
            for entry in schedule_d_entries:
                if entry["line"] == "Short 1256 portion":
                    entry["value"] = "12.34 USD"
                if entry["line"] == "Long 1256 portion":
                    entry["value"] = "87.66 USD"
                if entry["line"] == "Short total before Form 6781":
                    entry["value"] = "999.99 USD"
                if entry["line"] == "Long total before Form 6781":
                    entry["value"] = "888.88 USD"
            capital = final_output["usa"]["forms"]["capital_results"]["capital"]
            capital["section_1256_total_usd"] = "100.00"
            capital["section_1256_short_term_usd"] = "12.34"
            capital["section_1256_long_term_usd"] = "87.66"
            final_output_path.write_text(json.dumps(final_output))

            render_usa_forms(paths)

            schedule_d_text = (paths.usa_forms_root / "2025_schedule_d.md").read_text()
            form_6781_text = (paths.usa_forms_root / "2025_form_6781.md").read_text()

            self.assertIn("| Short 1256 portion | 12.34 USD | us-capital-results.json |", schedule_d_text)
            self.assertIn("| Long 1256 portion | 87.66 USD | us-capital-results.json |", schedule_d_text)
            self.assertIn("| Short total before Form 6781 | 999.99 USD | us-capital-results.json |", schedule_d_text)
            self.assertIn("| Long total before Form 6781 | 888.88 USD | us-capital-results.json |", schedule_d_text)
            self.assertIn("| 40% short-term portion | 12.34 USD | us-capital-results.json |", form_6781_text)
            self.assertIn("| 60% long-term portion | 87.66 USD | us-capital-results.json |", form_6781_text)

    def test_render_usa_schedule_d_requires_projected_final_output_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            final_output_path = write_final_legal_output_2025(paths)
            final_output = json.loads(final_output_path.read_text())
            final_output["usa"]["forms"].pop("schedule_d_entries")
            final_output_path.write_text(json.dumps(final_output))

            with self.assertRaisesRegex(FileNotFoundError, "schedule_d_entries"):
                render_usa_forms(paths)

    def test_render_usa_forms_consults_posture_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)

            with mock.patch("tax_pipeline.forms.usa.get_posture_definition", create=True) as mocked:
                _render_usa_forms_from_final(paths)

            mocked.assert_called_once_with("usa", "single")

    def test_render_usa_form_8960_uses_model_selected_niit_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            final_output_path = write_final_legal_output_2025(paths)
            final_output = json.loads(final_output_path.read_text())
            usa_forms = final_output["usa"]["forms"]
            usa_forms["treaty_package"]["chosen_position"]["filing_status"] = "Married filing jointly"
            usa_forms["treaty_package"]["chosen_position"]["joint_return_spouse_name"] = "Taylor North"
            usa_forms["treaty_package"]["chosen_position"]["joint_return_with_nra_spouse_election"] = "yes"
            usa_forms["tax_estimate"]["filing_assumptions"]["filing_status"] = "Married filing jointly"
            usa_forms["tax_estimate"]["filing_assumptions"]["joint_return_spouse_name"] = "Taylor North"
            usa_forms["tax_estimate"]["filing_assumptions"]["joint_return_with_nra_spouse_election"] = "yes"
            usa_forms["tax_estimate"]["filing_assumptions"]["niit_threshold_usd"] = "250000.00"
            final_output_path.write_text(json.dumps(final_output))

            render_usa_forms(paths)

            form_8960_text = (paths.usa_forms_root / "2025_form_8960.md").read_text()
            self.assertIn(
                "| Selected NIIT threshold | 250000.00 USD | us-tax-estimate.json | Model-selected threshold used for the 26 U.S.C. § 1411 NIIT calculation. |",
                form_8960_text,
            )
            self.assertNotIn("| MFS threshold | 125000.00 USD |", form_8960_text)
            self.assertNotIn("us-tax-constants.csv", form_8960_text)

    def test_render_usa_form_8960_fails_when_model_selected_niit_threshold_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            final_output_path = write_final_legal_output_2025(paths)
            final_output = json.loads(final_output_path.read_text())
            final_output["usa"]["forms"]["tax_estimate"]["filing_assumptions"].pop("niit_threshold_usd")
            final_output_path.write_text(json.dumps(final_output))

            with self.assertRaisesRegex(
                ValueError,
                "usa.forms.tax_estimate.filing_assumptions.niit_threshold_usd",
            ):
                render_usa_forms(paths)

    def test_render_usa_forms_fails_when_final_output_lacks_passive_dividend_ftc_support_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            write_final_legal_output_2025(paths)
            final_output_path = paths.analysis_root / "final-legal-output.json"
            final_output = json.loads(final_output_path.read_text())
            ftc_support_rows = final_output["usa"]["forms"]["ftc_support_rows"]
            final_output["usa"]["forms"]["ftc_support_rows"] = [
                row for row in ftc_support_rows if row["key"] != "foreign_source_passive_dividends_usd"
            ]
            final_output_path.write_text(json.dumps(final_output))

            with self.assertRaisesRegex(
                FileNotFoundError,
                "Missing required row foreign_source_passive_dividends_usd in usa/ftc-support.csv",
            ):
                render_usa_forms(paths)

    def test_render_usa_forms_fails_when_final_output_duplicates_passive_dividend_ftc_support_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)
            write_final_legal_output_2025(paths)
            final_output_path = paths.analysis_root / "final-legal-output.json"
            final_output = json.loads(final_output_path.read_text())
            ftc_support_rows = final_output["usa"]["forms"]["ftc_support_rows"]
            passive_dividend_row = next(row for row in ftc_support_rows if row["key"] == "foreign_source_passive_dividends_usd")
            ftc_support_rows.append(dict(passive_dividend_row))
            final_output_path.write_text(json.dumps(final_output))

            with self.assertRaisesRegex(
                ValueError,
                "Expected exactly one row for foreign_source_passive_dividends_usd in usa/ftc-support.csv",
            ):
                render_usa_forms(paths)

    def test_render_usa_forms_shows_balance_due_when_result_is_negative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_analysis_outputs(paths)

            treaty_path = paths.analysis_root / "us-treaty-package.json"
            estimate_path = paths.analysis_root / "us-tax-estimate.json"
            treaty = json.loads(treaty_path.read_text())
            estimate = json.loads(estimate_path.read_text())
            treaty["form_1040"]["line_35a_refund_usd"] = "0.00"
            treaty["form_1040"]["line_37_amount_owed_usd"] = "12.34"
            treaty["headline"]["refund_usd"] = "0.00"
            estimate["payments"]["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"] = "-12.34"
            estimate["payments"]["refund_if_positive_else_balance_due_usd"] = "-1.00"
            estimate["payments"]["refund_with_treaty_resourcing_usd"] = "0.00"
            estimate["payments"]["amount_owed_with_treaty_resourcing_usd"] = "12.34"
            estimate["payments"]["refund_without_treaty_resourcing_usd"] = "0.00"
            estimate["payments"]["amount_owed_without_treaty_resourcing_usd"] = "1.00"
            treaty_path.write_text(json.dumps(treaty))
            estimate_path.write_text(json.dumps(estimate))

            _render_usa_forms_from_final(paths)

            index_text = (paths.usa_forms_root / "index.md").read_text()
            form_1040_text = (paths.usa_forms_root / "2025_1040.md").read_text()

            self.assertIn("Final modeled result: **12.34 USD balance due**.", index_text)
            self.assertIn("| Line 35a | 0.00 USD | us-treaty-package.json | Refund amount; zero when the chosen treaty posture has a balance due. |", form_1040_text)
            self.assertIn("| Line 37 | 12.34 USD | us-treaty-package.json | Amount owed in the chosen treaty re-sourcing posture. |", form_1040_text)

class TestLegalAuditOutputs(unittest.TestCase):
    def _seed_germany_legal_outputs(self, paths: YearPaths) -> None:
        materialized = populate_demo_workspace(paths.project_root, year=paths.year)
        self.assertEqual(materialized.year_root, paths.year_root)

    def _seed_minimal_germany_legal_outputs(self, paths: YearPaths, *, filing_posture: str) -> None:
        paths.ensure_directories()
        results = {
            "ordinary": {"filing_posture": filing_posture},
            "refunds": {"final_target_refund_eur": "0.00"},
        }
        overview_text = (
            "# Germany 2025 Legal Audit Note\n\n"
            "## Manual Factual Positions Still Explicitly Configured\n"
            "- Synthetic test position.\n"
        )
        if filing_posture == "married_joint":
            joint_income_reference = "§ 26b EStG; § 32a Abs. 1 und 5 EStG; BMF Programmablaufplan 2025"
            joint_income_note = "Tariff income tax under the 2025 splitting tariff"
        else:
            joint_income_reference = "§ 32a Abs. 1 EStG; BMF Programmablaufplan 2025"
            joint_income_note = "Tariff income tax under the 2025 basic tariff"
        (paths.analysis_root / "final-legal-output.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "tax_year": paths.year,
                    "source_role": "minimal legal-audit fixture",
                    "germany": {
                        "legal_audit": {
                            "results": results,
                            "overview_text": overview_text,
                            "trace_rows": [
                                {
                                    "step": "joint_assessment_order",
                                    "value_eur": "0.00",
                                    "note": f"{filing_posture} posture",
                                    "legal_reference": "§ 26 EStG",
                                    "authority_url": "https://www.gesetze-im-internet.de/estg/__26.html",
                                    "precision_note": "",
                                },
                                {
                                    "step": "joint_income_tax",
                                    "value_eur": "0.00",
                                    "note": joint_income_note,
                                    "legal_reference": joint_income_reference,
                                    "authority_url": "https://www.gesetze-im-internet.de/estg/__32a.html",
                                    "precision_note": "",
                                },
                            ],
                            "assumption_rows": [
                                {
                                    "section": "synthetic",
                                    "key": "fixture",
                                    "value": "yes",
                                    "source": "test",
                                    "note": "Legal-audit fixture.",
                                }
                            ],
                        }
                    },
                }
            )
        )

    def _seed_usa_legal_outputs(self, paths: YearPaths) -> None:
        materialized = populate_demo_workspace(paths.project_root, year=paths.year)
        self.assertEqual(materialized.year_root, paths.year_root)

    def test_render_germany_legal_audit_writes_audit_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_legal_outputs(paths)

            render_germany_legal_audit(paths)

            expected_files = [
                paths.germany_legal_audit_root / "index.md",
                paths.germany_legal_audit_root / "overview.md",
                paths.germany_legal_audit_root / "law-matrix.csv",
                paths.germany_legal_audit_root / "law-matrix.md",
                paths.germany_legal_audit_root / "assumptions.md",
                paths.germany_legal_audit_root / "trace-index.md",
            ]
            for path in expected_files:
                self.assertTrue(path.exists(), path)

            index_text = (paths.germany_legal_audit_root / "index.md").read_text()
            overview_text = (paths.germany_legal_audit_root / "overview.md").read_text()
            assumptions_text = (paths.germany_legal_audit_root / "assumptions.md").read_text()
            trace_text = (paths.germany_legal_audit_root / "trace-index.md").read_text()
            matrix_text = (paths.germany_legal_audit_root / "law-matrix.md").read_text()

            self.assertIn("Final modeled result: **88.29 EUR balance due**.", index_text)
            self.assertIn("[law-matrix.md](law-matrix.md)", index_text)
            self.assertIn("# Germany 2025 Legal Audit Note", overview_text)
            self.assertIn("Separate Germany treaty-level dividend credits", assumptions_text)
            self.assertIn("Home-office day counts", assumptions_text)
            self.assertIn("| 1 | joint_assessment_order | 0.00 |", trace_text)
            self.assertIn("§ 32a Abs. 1 EStG", matrix_text)
            self.assertIn("Law Spec", matrix_text)
            self.assertIn("Test Coverage", matrix_text)
            self.assertIn("tax_pipeline/law_spec/germany/2025/basic_tariff.md", matrix_text)
            self.assertIn("tests/test_germany_2025_law.py", matrix_text)

    def test_render_germany_legal_audit_has_married_joint_split_tariff_fixture(self) -> None:
        # § 26b EStG and § 32a Abs. 5 EStG must be visible end-to-end in a married-joint
        # legal audit package, not only in unit-level trace enrichment.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            self._seed_minimal_germany_legal_outputs(paths, filing_posture="married_joint")

            render_germany_legal_audit(paths)

            matrix_text = (paths.germany_legal_audit_root / "law-matrix.md").read_text()
            trace_text = (paths.germany_legal_audit_root / "trace-index.md").read_text()

        self.assertIn("tax_pipeline/law_spec/germany/2025/split_tariff.md", matrix_text)
        self.assertIn("§ 26b EStG; § 32a Abs. 1 und 5 EStG", matrix_text)
        self.assertIn("joint_income_tax", trace_text)

    def test_render_germany_legal_audit_rejects_unsupported_married_separate_posture(self) -> None:
        # § 26a EStG separate assessment is not implemented by the 2025 Germany outputs;
        # the audit package must fail closed instead of presenting unsupported calculations.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            self._seed_minimal_germany_legal_outputs(paths, filing_posture="married_separate")

            with self.assertRaisesRegex(NotImplementedError, "married_separate"):
                render_germany_legal_audit(paths)

    def test_render_usa_legal_audit_writes_audit_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_legal_outputs(paths)

            _render_usa_legal_audit_from_final(paths)

            expected_files = [
                paths.usa_legal_audit_root / "index.md",
                paths.usa_legal_audit_root / "overview.md",
                paths.usa_legal_audit_root / "law-matrix.csv",
                paths.usa_legal_audit_root / "law-matrix.md",
                paths.usa_legal_audit_root / "assumptions.md",
                paths.usa_legal_audit_root / "trace-index.md",
            ]
            for path in expected_files:
                self.assertTrue(path.exists(), path)

            index_text = (paths.usa_legal_audit_root / "index.md").read_text()
            overview_text = (paths.usa_legal_audit_root / "overview.md").read_text()
            assumptions_text = (paths.usa_legal_audit_root / "assumptions.md").read_text()
            trace_text = (paths.usa_legal_audit_root / "trace-index.md").read_text()
            matrix_text = (paths.usa_legal_audit_root / "law-matrix.md").read_text()

            self.assertIn("Final modeled result: **778.08 USD refund**.", index_text)
            self.assertIn("[assumptions.md](assumptions.md)", index_text)
            self.assertIn("# U.S. 2025 Legal Audit Note", overview_text)
            self.assertIn("Allocate joint German wage-side tax by wage share", assumptions_text)
            self.assertIn("| 1 | eur_per_usd_yearly_average_2025 | 0.886 |", trace_text)
            self.assertIn("Germany treaty technical explanation; IRS Publication 514", matrix_text)
            self.assertIn("https://www.irs.gov/pub/irs-trty/germtech.pdf", matrix_text)

    def test_render_germany_legal_audit_fails_when_required_manual_section_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_legal_outputs(paths)

            audit_path = paths.analysis_root / "germany-audit-note.md"
            audit_text = audit_path.read_text().replace(
                "## Manual Factual Positions Still Explicitly Configured",
                "## Renamed Manual Positions",
            )
            audit_path.write_text(audit_text)

            with self.assertRaisesRegex(ValueError, "Missing required audit section heading"):
                _render_germany_legal_audit_from_final(paths)

    def test_render_germany_legal_audit_preserves_previous_package_on_failed_rerender(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_legal_outputs(paths)

            _render_germany_legal_audit_from_final(paths)
            original_index = (paths.germany_legal_audit_root / "index.md").read_text()
            original_overview = (paths.germany_legal_audit_root / "overview.md").read_text()

            trace_path = paths.analysis_root / "germany-model-trace.csv"
            broken_trace = trace_path.read_text().replace("legal_reference,", "", 1)
            trace_path.write_text(broken_trace)

            with self.assertRaisesRegex(ValueError, "Malformed CSV row in germany-model-trace.csv"):
                _render_germany_legal_audit_from_final(paths)

            self.assertEqual((paths.germany_legal_audit_root / "index.md").read_text(), original_index)
            self.assertEqual((paths.germany_legal_audit_root / "overview.md").read_text(), original_overview)

    def test_render_germany_legal_audit_fails_when_trace_has_blank_required_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_legal_outputs(paths)

            trace_path = paths.analysis_root / "germany-model-trace.csv"
            rows = list(csv.DictReader(trace_path.read_text().splitlines()))
            rows[0]["legal_reference"] = ""
            trace_buffer = io.StringIO(newline="")
            writer = csv.DictWriter(
                trace_buffer,
                fieldnames=["step", "value_eur", "legal_reference", "authority_url", "note", "precision_note"],
            )
            writer.writeheader()
            writer.writerows(rows)
            trace_path.write_text(trace_buffer.getvalue())

            with self.assertRaisesRegex(ValueError, "Missing required values for germany-model-trace.csv: row 1:legal_reference"):
                _render_germany_legal_audit_from_final(paths)

    def test_render_germany_legal_audit_fails_when_assumptions_schema_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_germany_legal_outputs(paths)

            assumptions_path = paths.tax_positions_root / "de-model-assumptions.csv"
            broken_assumptions = assumptions_path.read_text().replace("section,key,value,source,note", "key,value,source,note", 1)
            assumptions_path.write_text(broken_assumptions)

            with self.assertRaisesRegex(ValueError, "Malformed CSV row in de-model-assumptions.csv"):
                _render_germany_legal_audit_from_final(paths)

    def test_render_usa_legal_audit_fails_when_trace_is_missing_legal_reference_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_legal_outputs(paths)

            trace_path = paths.analysis_root / "us-tax-trace.csv"
            broken_trace = trace_path.read_text().replace("legal_reference,", "", 1)
            trace_path.write_text(broken_trace)

            with self.assertRaisesRegex(ValueError, "Malformed CSV row in us-tax-trace.csv"):
                _render_usa_legal_audit_from_final(paths)

    def test_render_usa_legal_audit_fails_when_assumptions_have_blank_required_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            self._seed_usa_legal_outputs(paths)

            assumptions_path = paths.tax_positions_root / "us-model-assumptions.csv"
            rows = list(csv.DictReader(assumptions_path.read_text().splitlines()))
            rows[0]["note"] = ""
            assumptions_buffer = io.StringIO(newline="")
            writer = csv.DictWriter(assumptions_buffer, fieldnames=["section", "key", "value", "source", "note"])
            writer.writeheader()
            writer.writerows(rows)
            assumptions_path.write_text(assumptions_buffer.getvalue())

            with self.assertRaisesRegex(ValueError, "Missing required values for us-model-assumptions.csv: row 1:note"):
                _render_usa_legal_audit_from_final(paths)
