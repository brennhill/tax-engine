from __future__ import annotations

import csv
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.y2025.us_law import (
    MFS_CAPITAL_LOSS_LIMIT_USD,
    STANDARD_CAPITAL_LOSS_LIMIT_USD,
    USTaxConstants2025,
    form_1040_whole_dollar_2025,
    regular_tax_2025,
    tax_from_schedule_y2_2025,
    taxable_income_2025,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "usa" / "irs_ats_2025"
IRS_ATS_PAGE_URL = (
    "https://www.irs.gov/e-file-providers/"
    "tax-year-2025-form-1040-series-and-extensions-modernized-e-file-mef-assurance-testing-system-ats-information"
)


def _constants_for_filing_status(filing_status: str) -> USTaxConstants2025:
    if filing_status == "single":
        return USTaxConstants2025(
            eur_per_usd_yearly_average_2025=Decimal("0.886"),
            standard_deduction_2025_usd=Decimal("15750.00"),
            capital_loss_limit_usd=STANDARD_CAPITAL_LOSS_LIMIT_USD,
            niit_threshold_usd=Decimal("200000.00"),
            qualified_dividend_zero_rate_ceiling_2025_usd=Decimal("48350.00"),
            qualified_dividend_fifteen_rate_ceiling_2025_usd=Decimal("533400.00"),
            tax_bracket_10_ceiling_2025_usd=Decimal("11925.00"),
            tax_bracket_12_ceiling_2025_usd=Decimal("48475.00"),
            tax_bracket_22_ceiling_2025_usd=Decimal("103350.00"),
            tax_bracket_24_ceiling_2025_usd=Decimal("197300.00"),
            tax_bracket_32_ceiling_2025_usd=Decimal("250525.00"),
            tax_bracket_35_ceiling_2025_usd=Decimal("626350.00"),
        )
    if filing_status == "married_joint":
        return USTaxConstants2025(
            eur_per_usd_yearly_average_2025=Decimal("0.886"),
            standard_deduction_2025_usd=Decimal("31500.00"),
            capital_loss_limit_usd=STANDARD_CAPITAL_LOSS_LIMIT_USD,
            niit_threshold_usd=Decimal("250000.00"),
            qualified_dividend_zero_rate_ceiling_2025_usd=Decimal("96700.00"),
            qualified_dividend_fifteen_rate_ceiling_2025_usd=Decimal("600050.00"),
            tax_bracket_10_ceiling_2025_usd=Decimal("23850.00"),
            tax_bracket_12_ceiling_2025_usd=Decimal("96950.00"),
            tax_bracket_22_ceiling_2025_usd=Decimal("206700.00"),
            tax_bracket_24_ceiling_2025_usd=Decimal("394600.00"),
            tax_bracket_32_ceiling_2025_usd=Decimal("501050.00"),
            tax_bracket_35_ceiling_2025_usd=Decimal("751600.00"),
        )
    if filing_status == "married_separate":
        return USTaxConstants2025(
            eur_per_usd_yearly_average_2025=Decimal("0.886"),
            standard_deduction_2025_usd=Decimal("15750.00"),
            capital_loss_limit_usd=MFS_CAPITAL_LOSS_LIMIT_USD,
            niit_threshold_usd=Decimal("125000.00"),
            qualified_dividend_zero_rate_ceiling_2025_usd=Decimal("48350.00"),
            qualified_dividend_fifteen_rate_ceiling_2025_usd=Decimal("300000.00"),
            tax_bracket_10_ceiling_2025_usd=Decimal("11925.00"),
            tax_bracket_12_ceiling_2025_usd=Decimal("48475.00"),
            tax_bracket_22_ceiling_2025_usd=Decimal("103350.00"),
            tax_bracket_24_ceiling_2025_usd=Decimal("197300.00"),
            tax_bracket_32_ceiling_2025_usd=Decimal("250525.00"),
            tax_bracket_35_ceiling_2025_usd=Decimal("375800.00"),
        )
    raise AssertionError(f"unsupported ATS fixture filing status: {filing_status}")


class USA2025IRSATSGoldenSourcesTest(unittest.TestCase):
    def test_irs_ats_2025_source_index_lists_official_scenario_pdfs(self) -> None:
        fixture_path = FIXTURE_ROOT / "source-options.csv"
        self.assertTrue(fixture_path.exists(), fixture_path)

        rows = list(csv.DictReader(fixture_path.read_text(encoding="utf-8").splitlines()))
        self.assertGreaterEqual(len(rows), 10)
        source_ids = {row["source_id"] for row in rows}
        self.assertIn("irs_ats_2025_1040_scenario_12", source_ids)
        self.assertIn("irs_ats_2025_1040_scenario_13", source_ids)
        for row in rows:
            with self.subTest(source_id=row["source_id"]):
                self.assertEqual(row["source_page_url"], IRS_ATS_PAGE_URL)
                self.assertTrue(row["pdf_url"].startswith("https://www.irs.gov/pub/irs-efile/"), row["pdf_url"])
                self.assertIn(row["return_family"], {"1040", "1040-SR", "1040-SS", "1040-NR", "4868"})
                self.assertIn(row["engine_supported_now"], {"true", "false"})
                self.assertIn(row["contains_completed_form1040_outputs"], {"true", "false"})

    def test_irs_ats_2025_expected_form1040_lines_are_numeric_and_source_linked(self) -> None:
        source_rows = {
            row["source_id"]: row
            for row in csv.DictReader((FIXTURE_ROOT / "source-options.csv").read_text(encoding="utf-8").splitlines())
        }
        fixture_path = FIXTURE_ROOT / "expected-form1040-lines.csv"
        self.assertTrue(fixture_path.exists(), fixture_path)

        rows = list(csv.DictReader(fixture_path.read_text(encoding="utf-8").splitlines()))
        self.assertGreaterEqual(len(rows), 25)
        scenarios_with_outputs = {row["source_id"] for row in rows}
        self.assertEqual(
            scenarios_with_outputs,
            {
                "irs_ats_2025_1040_scenario_12",
                "irs_ats_2025_1040_scenario_13",
            },
        )
        for row in rows:
            with self.subTest(source_id=row["source_id"], form=row["form"], line=row["line"]):
                self.assertIn(row["source_id"], source_rows)
                self.assertEqual(source_rows[row["source_id"]]["contains_completed_form1040_outputs"], "true")
                self.assertEqual(row["form"], "Form 1040")
                self.assertRegex(row["line"], r"^[0-9]{1,2}[a-z]?$")
                self.assertRegex(row["expected_value_usd"], r"^-?[0-9]+(\.[0-9]{2})?$")
                self.assertTrue(row["source_pdf_url"].startswith("https://www.irs.gov/pub/irs-efile/"))
                self.assertIn("official IRS ATS", row["source_note"])

    def test_covered_irs_ats_cases_execute_against_supported_us_engine_logic(self) -> None:
        source_rows = {
            row["source_id"]: row
            for row in csv.DictReader((FIXTURE_ROOT / "source-options.csv").read_text(encoding="utf-8").splitlines())
        }
        expected_lines = {
            (row["source_id"], row["line"]): Decimal(row["expected_value_usd"])
            for row in csv.DictReader((FIXTURE_ROOT / "expected-form1040-lines.csv").read_text(encoding="utf-8").splitlines())
        }
        rows = list(
            csv.DictReader((FIXTURE_ROOT / "covered-engine-cases.csv").read_text(encoding="utf-8").splitlines())
        )

        self.assertEqual({row["source_id"] for row in rows}, {
            "irs_ats_2025_1040_scenario_12",
            "irs_ats_2025_1040_scenario_13",
        })

        for row in rows:
            with self.subTest(source_id=row["source_id"]):
                self.assertEqual(source_rows[row["source_id"]]["engine_supported_now"], "true")
                self.assertEqual(source_rows[row["source_id"]]["contains_completed_form1040_outputs"], "true")
                self.assertEqual(Decimal(row["form_1040_line_15_taxable_income_usd"]), expected_lines[(row["source_id"], "15")])

                # 26 U.S.C. § 63 and Form 1040 line 15 define taxable income as
                # line 11b AGI minus line 14 deductions, floored at zero.
                taxable_income = taxable_income_2025(
                    Decimal(row["form_1040_line_11b_agi_usd"]),
                    Decimal(row["form_1040_line_14_deductions_usd"]),
                )
                self.assertEqual(taxable_income, Decimal(row["form_1040_line_15_taxable_income_usd"]))

                constants = _constants_for_filing_status(row["filing_status"])
                if row["form_1040_line_16_supported"] == "true":
                    # 26 U.S.C. § 1 and the 2025 Form 1040 line-16 instructions govern
                    # regular tax. The ATS Form 1040 prints whole-dollar line amounts,
                    # while the engine keeps cents in its supporting legal output.
                    raw_tax = regular_tax_2025(
                        taxable_income,
                        Decimal("0.00"),
                        constants,
                    ).regular_tax_before_credits_usd
                    self.assertEqual(
                        form_1040_whole_dollar_2025(raw_tax),
                        Decimal(row["form_1040_line_16_tax_usd"]),
                    )
                else:
                    self.assertEqual(row["form_1040_line_16_tax_usd"], "")
                    self.assertIn("Tax Table", row["line_16_exclusion_reason"])
                    self.assertEqual(expected_lines[(row["source_id"], "16")], Decimal("162.00"))
                    self.assertEqual(tax_from_schedule_y2_2025(taxable_income, constants), Decimal("161.00"))


if __name__ == "__main__":
    unittest.main()
