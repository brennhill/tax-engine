from __future__ import annotations

import csv
import fnmatch
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GERMANY_LAW_SPEC_ROOT = PROJECT_ROOT / "tax_pipeline" / "law_spec" / "germany" / "2025"
USA_LAW_SPEC_ROOT = PROJECT_ROOT / "tax_pipeline" / "law_spec" / "usa" / "2025"

from tax_pipeline.legal_audit.germany import _enrich_trace_rows_with_law_spec
from tests.generated_demo import GeneratedDemoWorkspace, generate_demo_workspace



def _coverage_rows(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        if not line.startswith("| "):
            continue
        if line.startswith("| Pattern |") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        pattern = cells[0].strip("`")
        spec_cell = cells[1]
        match = re.search(r"\(([^)]+)\)", spec_cell)
        if not match:
            raise ValueError(f"Coverage row missing markdown link target: {line}")
        rows.append((pattern, match.group(1)))
    return rows


def _trace_steps(path: Path) -> list[str]:
    with path.open(newline="") as handle:
        return [row["step"] for row in csv.DictReader(handle)]


class LawSpecCoverageTest(unittest.TestCase):
    demo: GeneratedDemoWorkspace

    @classmethod
    def setUpClass(cls) -> None:
        cls.demo = generate_demo_workspace()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.demo.cleanup()

    def test_germany_trace_steps_are_all_covered_by_law_spec_patterns(self) -> None:
        coverage = _coverage_rows(GERMANY_LAW_SPEC_ROOT / "coverage.md")
        for _, target in coverage:
            self.assertTrue((GERMANY_LAW_SPEC_ROOT / target).exists(), target)
        uncovered = [
            step
            for step in _trace_steps(self.demo.paths.analysis_root / "germany-model-trace.csv")
            if not any(fnmatch.fnmatch(step, pattern) for pattern, _ in coverage)
        ]
        self.assertEqual(uncovered, [])

    def test_germany_trace_law_references_match_single_demo_posture(self) -> None:
        trace_path = self.demo.paths.analysis_root / "germany-model-trace.csv"
        with trace_path.open(newline="") as handle:
            rows = {row["step"]: row for row in csv.DictReader(handle)}

        self.assertIn("filing posture single", rows["joint_assessment_order"]["note"])
        self.assertNotIn("§ 26b", rows["joint_assessment_order"]["legal_reference"])
        self.assertIn("§ 32a Abs. 1", rows["joint_income_tax"]["legal_reference"])
        self.assertNotIn("§ 32a Abs. 5", rows["joint_income_tax"]["legal_reference"])
        self.assertIn("not taxable because it does not reach", rows["other_income_22nr3_taxable"]["note"])
        self.assertNotIn("spouse bank-certificate", rows["final_target_refund"]["note"])

    def test_germany_2025_tariff_and_soli_specs_pin_dated_bmf_authority(self) -> None:
        # Live statute pages can show later-year constants; 2025 audit specs must pin the
        # dated BMF 2025 Programmablaufplan used for the § 32a tariff and SolzG thresholds.
        bmf_pap_2025 = "Programmablaufplan-2025"
        self.assertIn(bmf_pap_2025, (GERMANY_LAW_SPEC_ROOT / "basic_tariff.md").read_text())
        self.assertIn(bmf_pap_2025, (GERMANY_LAW_SPEC_ROOT / "split_tariff.md").read_text())
        self.assertIn(bmf_pap_2025, (GERMANY_LAW_SPEC_ROOT / "ordinary_soli.md").read_text())

    def test_germany_married_income_tax_trace_maps_to_split_tariff_spec(self) -> None:
        # § 26b EStG and § 32a Abs. 5 EStG married splitting must map to split_tariff.md
        # even when the trace cites the canonical combined text "§ 32a Abs. 1 und 5".
        rows = _enrich_trace_rows_with_law_spec(
            [
                {
                    "step": "joint_income_tax",
                    "value_eur": "100.00",
                    "note": "Tariff income tax under the 2025 splitting tariff",
                    "legal_reference": "§ 26b EStG; § 32a Abs. 1 und 5 EStG; BMF Programmablaufplan 2025",
                    "authority_url": "https://www.gesetze-im-internet.de/estg/__32a.html",
                    "precision_note": "",
                }
            ]
        )

        self.assertEqual(rows[0]["law_spec"], "tax_pipeline/law_spec/germany/2025/split_tariff.md")

    def test_germany_married_income_tax_trace_fails_closed_without_32a_5_reference(self) -> None:
        # § 26b EStG only determines married income tax through the § 32a Abs. 5 splitting
        # method; a married/splitting trace that omits Abs. 5 must not fall back to basic_tariff.md.
        with self.assertRaisesRegex(ValueError, "§ 32a Abs. 5"):
            _enrich_trace_rows_with_law_spec(
                [
                    {
                        "step": "joint_income_tax",
                        "value_eur": "100.00",
                        "note": "Tariff income tax under the 2025 splitting tariff",
                        "legal_reference": "§ 26b EStG; BMF Programmablaufplan 2025",
                        "authority_url": "https://www.gesetze-im-internet.de/estg/__32a.html",
                        "precision_note": "",
                    }
                ]
            )

    def test_germany_bank_certificate_trace_steps_map_to_spouse_certificate_spec(self) -> None:
        # § 20 Abs. 6/9, § 32d Abs. 5, and § 36 Abs. 2 Nr. 2 EStG require typed
        # bank-certificate facts to be part of the joint capital assessment. The
        # audit matrix must map both the income/credit stage and the final § 36
        # withholding-credit stage to the certificate law spec, with no legacy
        # sidecar status remaining.
        rows = _enrich_trace_rows_with_law_spec(
            [
                {
                    "step": "bank_certificate_capital_income",
                    "value_eur": "189.28",
                    "note": "Typed bank-certificate line 7 income included inside the joint § 20 capital base",
                    "legal_reference": "§ 20 Abs. 6/9 EStG; § 32d Abs. 5 EStG; § 36 Abs. 2 Nr. 2 EStG",
                    "authority_url": "https://www.gesetze-im-internet.de/estg/__20.html",
                    "precision_note": "Line 8 stock gains are treated as a subset of line 7.",
                },
                {
                    "step": "domestic_capital_withholding_credit",
                    "value_eur": "33.21",
                    "note": "Bank-certificate Kapitalertragsteuer and solidarity surcharge credited after capital tax is computed",
                    "legal_reference": "§ 36 Abs. 2 Nr. 2 EStG; § 4 SolzG 1995",
                    "authority_url": "https://www.gesetze-im-internet.de/estg/__36.html",
                    "precision_note": "",
                },
            ]
        )

        for row in rows:
            self.assertEqual(
                row["law_spec"],
                "tax_pipeline/law_spec/germany/2025/spouse_bank_capital_certificate.md",
            )
        coverage_text = Path("tax_pipeline/law_spec/germany/2025/coverage.md").read_text()
        self.assertNotIn("spouse_bank_certificate_sidecar_status", coverage_text)

    def test_germany_law_spec_index_and_ordering_cover_26_and_basic_tariff(self) -> None:
        # § 26 EStG is the legal gate for married assessment; basic_tariff.md is a first-class
        # law spec for single/separate traces and must be discoverable from the index.
        index = (GERMANY_LAW_SPEC_ROOT / "index.md").read_text()
        assessment_ordering = (GERMANY_LAW_SPEC_ROOT / "assessment_ordering.md").read_text()
        capital_spec = (GERMANY_LAW_SPEC_ROOT / "capital_buckets_and_saver_allowance.md").read_text()
        retirement_spec = (GERMANY_LAW_SPEC_ROOT / "retirement_contributions.md").read_text()

        self.assertIn("basic_tariff.md", index)
        self.assertIn("§ 26 EStG", assessment_ordering)
        self.assertIn("Teilfreistellung -> § 20 loss netting -> Sparer-Pauschbetrag -> § 32d tax", capital_spec)
        self.assertIn("esth/2025/tabellarische-Uebersicht/Vorsorgeaufwendunge.html", retirement_spec)

    def test_usa_trace_steps_are_all_covered_by_law_spec_patterns(self) -> None:
        coverage = _coverage_rows(USA_LAW_SPEC_ROOT / "coverage.md")
        for _, target in coverage:
            self.assertTrue((USA_LAW_SPEC_ROOT / target).exists(), target)
        uncovered = [
            step
            for step in _trace_steps(self.demo.paths.analysis_root / "us-tax-trace.csv")
            if not any(fnmatch.fnmatch(step, pattern) for pattern, _ in coverage)
        ]
        self.assertEqual(uncovered, [])
