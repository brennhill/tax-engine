"""§ 1 ordinary-bracket / § 1(h) preferential-rate tests.

Authority:
- 26 U.S.C. § 1 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1)
- 26 U.S.C. § 1(h) (https://www.law.cornell.edu/uscode/text/26/1)
- IRS Form 1040 line-16 instructions (Tax Table / Computation Worksheet)

Asserts identity with ``tax_pipeline.y2025.us_law`` for the bracket
helpers and the § 1(h) preferential rates.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p1 import (
    QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE,
    QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE,
    USC_1_URL,
    _tax_from_ordinary_brackets_2025,
    _tax_table_lookup_income_2025,
    tax_from_schedule_y2_2025,
    tax_from_schedule_y2_2025_mfs,
)
from tax_pipeline.y2025.us_law import (
    QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE as ORIG_15,
    QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE as ORIG_20,
    USC_1_URL as ORIG_URL,
    USTaxConstants2025,
    _tax_from_ordinary_brackets_2025 as orig_brackets,
    _tax_table_lookup_income_2025 as orig_table,
    tax_from_schedule_y2_2025 as orig_y2,
    tax_from_schedule_y2_2025_mfs as orig_y2_mfs,
)


def _mfj_constants_2025() -> USTaxConstants2025:
    # 2025 MFJ ordinary-bracket ceilings (Rev. Proc. 2024-40):
    #   10% to $23,850; 12% to $96,950; 22% to $206,700;
    #   24% to $394,600; 32% to $501,050; 35% to $751,600.
    # Preferential ceilings: 0% to $96,700; 15% to $600,050.
    return USTaxConstants2025(
        eur_per_usd_yearly_average_2025=Decimal("0.886"),
        standard_deduction_2025_usd=Decimal("30000.00"),
        capital_loss_limit_usd=Decimal("3000.00"),
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


class P1IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_1_URL, ORIG_URL)

    def test_15_rate_matches_production(self) -> None:
        self.assertEqual(QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE, ORIG_15)
        self.assertEqual(
            QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE, Decimal("0.15")
        )

    def test_20_rate_matches_production(self) -> None:
        self.assertEqual(QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE, ORIG_20)
        self.assertEqual(
            QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE, Decimal("0.20")
        )

    def test_table_lookup_matches_production(self) -> None:
        for income in (
            Decimal("4.99"),
            Decimal("17.50"),
            Decimal("123.00"),
            Decimal("2999.99"),
            Decimal("12345.00"),
            Decimal("99999.99"),
        ):
            self.assertEqual(
                _tax_table_lookup_income_2025(income),
                orig_table(income),
                msg=f"income={income}",
            )

    def test_brackets_match_production(self) -> None:
        constants = _mfj_constants_2025()
        for income in (
            Decimal("100000.00"),
            Decimal("250000.00"),
            Decimal("500000.00"),
            Decimal("800000.00"),
        ):
            self.assertEqual(
                _tax_from_ordinary_brackets_2025(income, constants),
                orig_brackets(income, constants),
                msg=f"income={income}",
            )

    def test_y2_matches_production(self) -> None:
        constants = _mfj_constants_2025()
        for income in (
            Decimal("0.00"),
            Decimal("17.50"),
            Decimal("12345.00"),
            Decimal("100000.00"),
            Decimal("250000.00"),
            Decimal("500000.00"),
        ):
            self.assertEqual(
                tax_from_schedule_y2_2025(income, constants),
                orig_y2(income, constants),
                msg=f"income={income}",
            )
            self.assertEqual(
                tax_from_schedule_y2_2025_mfs(income, constants),
                orig_y2_mfs(income, constants),
                msg=f"income={income}",
            )

    def test_negative_income_fails_closed(self) -> None:
        constants = _mfj_constants_2025()
        with self.assertRaises(ValueError):
            tax_from_schedule_y2_2025(Decimal("-1.00"), constants)


if __name__ == "__main__":
    unittest.main()
