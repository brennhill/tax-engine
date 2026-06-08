from __future__ import annotations

import csv
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.y2025.germany_law import (
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    compute_joint_ordinary_assessment_2025,
    german_income_tax_single_2025,
    german_income_tax_split_2025,
    german_soli_assessment_2025,
)

FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "germany"
BMF_2025_XML_URL = "https://bmf-steuerrechner.de/javax.faces.resource/daten/xmls/Lohnsteuer2025.xml.xhtml"
BMF_EKST_RECHNER_URL = "https://www.bmf-steuerrechner.de/ekst/eingabeformekst.xhtml"
ESTG_32A_URL = "https://www.gesetze-im-internet.de/estg/__32a.html"
SOLZG_3_URL = "https://www.gesetze-im-internet.de/solzg_1995/__3.html"
SOLZG_4_URL = "https://www.gesetze-im-internet.de/solzg_1995/__4.html"


class Germany2025GoldenSourcesTest(unittest.TestCase):
    def test_bmf_2025_tariff_and_soli_golden_samples_match_source_fixture(self) -> None:
        # Sources: BMF 2025 XML-Pseudocode UPTAB25/MSOLZ, BMF ESt calculator note that
        # the ESt calculator computes only § 32a tariff tax from zvE, and SolzG §§ 3-4.
        fixture_path = FIXTURE_ROOT / "bmf_2025_tariff_and_soli_samples.csv"
        self.assertTrue(fixture_path.exists(), fixture_path)

        rows = list(csv.DictReader(fixture_path.read_text(encoding="utf-8").splitlines()))
        self.assertGreaterEqual(len(rows), 24)
        for row in rows:
            with self.subTest(case_id=row["case_id"]):
                sources = {item.strip() for item in row["source_urls"].split(";")}
                self.assertIn(BMF_2025_XML_URL, sources)
                self.assertIn(BMF_EKST_RECHNER_URL, sources)
                self.assertIn(ESTG_32A_URL, sources)
                self.assertIn(SOLZG_3_URL, sources)
                self.assertIn(SOLZG_4_URL, sources)

                zve = Decimal(row["zve_eur"])
                expected_income_tax = Decimal(row["expected_income_tax_eur"])
                expected_soli = Decimal(row["expected_soli_eur"])

                if row["filing_posture"] == "single":
                    income_tax = german_income_tax_single_2025(zve)
                elif row["filing_posture"] == "married_joint":
                    income_tax = german_income_tax_split_2025(zve)
                else:
                    self.fail(f"unsupported filing_posture in BMF fixture: {row['filing_posture']}")

                self.assertEqual(income_tax, expected_income_tax)
                self.assertEqual(
                    german_soli_assessment_2025(income_tax, filing_posture=row["filing_posture"]),
                    expected_soli,
                )

    def test_datev_sample_options_are_indexed_without_committed_proprietary_case_values(self) -> None:
        # Source: DATEV's public product page documents the available education cases,
        # required DATEV Einkommensteuer comfort software, sample data, forms, calculations,
        # and Musterloesung availability. The actual case contents stay external.
        fixture_path = FIXTURE_ROOT / "datev" / "source-options.csv"
        self.assertTrue(fixture_path.exists(), fixture_path)

        rows = list(csv.DictReader(fixture_path.read_text(encoding="utf-8").splitlines()))
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            with self.subTest(source_id=row["source_id"]):
                self.assertTrue(row["url"].startswith("https://www.datev.de/"), row["url"])
                self.assertEqual(row["redistributable_in_repo"], "false")
                self.assertIn(row["contains_expected_outputs"], {"true", "false", "unknown"})
                self.assertNotIn("expected_income_tax_eur", row)
                self.assertNotIn("expected_balance_eur", row)

    def test_user_provided_datev_golden_cases_check_engine_outputs(self) -> None:
        # DATEV's public pages confirm that their teaching cases include Musterloesung,
        # Berechnungslisten, forms, and software control data. The exact purchased case
        # values are intentionally loaded from a user-provided CSV rather than copied into
        # the public repo.
        default_path = FIXTURE_ROOT / "datev" / "provided_golden_cases.csv"
        fixture_path = Path(os.environ.get("DATEV_GERMANY_2025_GOLDEN_CASES", default_path))
        if not fixture_path.exists():
            self.skipTest(f"DATEV golden cases not provided at {fixture_path}")

        rows = list(csv.DictReader(fixture_path.read_text(encoding="utf-8").splitlines()))
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            with self.subTest(case_id=row["case_id"]):
                self.assertTrue(row["source_url"].startswith("https://www.datev.de/"))
                assessment = compute_joint_ordinary_assessment_2025(
                    JointOrdinaryInputs2025(
                        people=self._people_from_datev_row(row),
                        other_income_22nr3_eur=self._decimal(row, "other_income_22nr3_eur"),
                        other_income_22nr3_threshold_eur=self._decimal(
                            row,
                            "other_income_22nr3_threshold_eur",
                            default="256.00",
                        ),
                        prepayments_eur=self._decimal(row, "prepayments_eur"),
                        filing_posture=row["filing_posture"],
                        # DATEV fixture rows marked married_joint are legal golden cases for § 26b
                        # / § 32a Abs. 5 checks, so the § 26 eligibility gate is part of the fixture.
                        joint_assessment_prerequisites_validated=row["filing_posture"] == "married_joint",
                    )
                )

                self.assertEqual(
                    assessment.joint_taxable_income_eur,
                    self._decimal(row, "expected_joint_taxable_income_eur"),
                )
                self.assertEqual(
                    assessment.joint_income_tax_eur,
                    self._decimal(row, "expected_joint_income_tax_eur"),
                )
                self.assertEqual(
                    assessment.joint_solidarity_surcharge_eur,
                    self._decimal(row, "expected_joint_soli_eur"),
                )
                self.assertEqual(
                    assessment.ordinary_refund_before_capital_eur,
                    self._decimal(row, "expected_ordinary_refund_before_capital_eur"),
                )

    def _people_from_datev_row(self, row: dict[str, str]) -> tuple[PersonOrdinaryInputs2025, ...]:
        people_count = int(row.get("people_count") or ("1" if row["filing_posture"] == "single" else "2"))
        return tuple(self._person_from_datev_row(row, index) for index in range(1, people_count + 1))

    def _person_from_datev_row(self, row: dict[str, str], index: int) -> PersonOrdinaryInputs2025:
        prefix = f"person_{index}_"
        slot = f"person_{index}"
        return PersonOrdinaryInputs2025(
            slot=slot,
            order_label=f"DATEV person {index}",
            display_name=row.get(f"{prefix}display_name") or f"DATEV person {index}",
            owner=slot,
            wage=WageFacts2025(
                owner=slot,
                source_files=(row["source_reference"],),
                gross_wage_eur=self._decimal(row, f"{prefix}gross_wage_eur"),
                withheld_wage_tax_eur=self._decimal(row, f"{prefix}withheld_wage_tax_eur"),
                withheld_solidarity_surcharge_eur=self._decimal(
                    row,
                    f"{prefix}withheld_solidarity_surcharge_eur",
                ),
                multiannual_wage_eur=self._decimal(row, f"{prefix}multiannual_wage_eur"),
                employer_pension_contribution_eur=self._decimal(row, f"{prefix}employer_pension_contribution_eur"),
                employee_pension_contribution_eur=self._decimal(row, f"{prefix}employee_pension_contribution_eur"),
                employee_health_insurance_eur=self._decimal(row, f"{prefix}employee_health_insurance_eur"),
                employee_nursing_care_insurance_eur=self._decimal(row, f"{prefix}employee_nursing_care_insurance_eur"),
                employee_unemployment_insurance_eur=self._decimal(row, f"{prefix}employee_unemployment_insurance_eur"),
            ),
            work_equipment_items=(),
            home_office_days_without_visit=int(row.get(f"{prefix}home_office_days_without_visit") or "0"),
            home_office_days_with_visit=int(row.get(f"{prefix}home_office_days_with_visit") or "0"),
            manual_work_equipment_deduction_eur=self._decimal(row, f"{prefix}manual_work_equipment_deduction_eur"),
            telecom_deduction_eur=self._decimal(row, f"{prefix}telecom_deduction_eur"),
            employment_legal_insurance_deduction_eur=self._decimal(
                row,
                f"{prefix}employment_legal_insurance_deduction_eur",
            ),
            cross_border_tax_help_deduction_eur=self._decimal(row, f"{prefix}cross_border_tax_help_deduction_eur"),
            health_insurance_sick_pay_reduction_rate=self._decimal(
                row,
                f"{prefix}health_insurance_sick_pay_reduction_rate",
                default="0.04",
            ),
        )

    def _decimal(self, row: dict[str, str], key: str, *, default: str = "0.00") -> Decimal:
        value = row.get(key, "")
        return Decimal(value if value != "" else default)


if __name__ == "__main__":
    unittest.main()
