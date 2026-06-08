"""§ 904 FTC limitation tests.

Authority:
- 26 U.S.C. § 904 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904)
- IRS Form 1116 instructions (https://www.irs.gov/instructions/i1116)
- IRS Pub. 514 (https://www.irs.gov/publications/p514)

Asserts identity with the production module's § 904 helper chain.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p904 import (
    USC_904_URL,
    current_year_general_foreign_tax_usd_2025,
    ftc_limitation_2025,
    standard_deduction_allocation_2025,
    total_gross_income_for_ftc_2025,
    validate_documented_positive_income_denominator_bound_2025,
)
from tax_pipeline.y2025.us_law import (
    USC_904_URL as ORIG_URL,
    current_year_general_foreign_tax_usd_2025 as orig_wage_share,
    ftc_limitation_2025 as orig_lim,
    standard_deduction_allocation_2025 as orig_alloc,
    total_gross_income_for_ftc_2025 as orig_total,
    validate_documented_positive_income_denominator_bound_2025 as orig_validate,
)


class P904IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_904_URL, ORIG_URL)

    def test_total_gross_income_matches_production(self) -> None:
        kwargs = dict(
            wages_usd=Decimal("100000.00"),
            ordinary_dividends_usd=Decimal("5000.00"),
            interest_income_usd=Decimal("250.00"),
            schedule_1_other_income_usd=Decimal("100.00"),
            capital_gain_distributions_usd=Decimal("250.00"),
            known_positive_short_capital_gain_usd=Decimal("0.00"),
            known_positive_long_capital_gain_usd=Decimal("750.00"),
        )
        self.assertEqual(
            total_gross_income_for_ftc_2025(**kwargs),
            orig_total(**kwargs),
        )

    def test_standard_deduction_allocation_matches_production(self) -> None:
        kwargs = dict(
            standard_deduction_usd=Decimal("30000.00"),
            category_gross_income_usd=Decimal("90000.00"),
            total_gross_income_for_ftc_usd=Decimal("100000.00"),
        )
        self.assertEqual(
            standard_deduction_allocation_2025(**kwargs),
            orig_alloc(**kwargs),
        )

    def test_ftc_limitation_matches_production(self) -> None:
        kwargs = dict(
            regular_tax_before_credits_usd=Decimal("12000.00"),
            category_taxable_income_usd=Decimal("60000.00"),
            taxable_income_usd=Decimal("80000.00"),
        )
        self.assertEqual(
            ftc_limitation_2025(**kwargs),
            orig_lim(**kwargs),
        )
        # 12000 × 60/80 = 9000
        self.assertEqual(
            ftc_limitation_2025(**kwargs), Decimal("9000.0000")
        )

    def test_ftc_limitation_caps_at_pre_credit_tax(self) -> None:
        kwargs = dict(
            regular_tax_before_credits_usd=Decimal("12000.00"),
            category_taxable_income_usd=Decimal("80000.00"),
            taxable_income_usd=Decimal("60000.00"),
        )
        # Foreign-source > worldwide → fraction > 1.0; cap at $12,000.
        self.assertEqual(
            ftc_limitation_2025(**kwargs),
            orig_lim(**kwargs),
        )

    def test_zero_taxable_income_returns_zero(self) -> None:
        result = ftc_limitation_2025(
            regular_tax_before_credits_usd=Decimal("0.00"),
            category_taxable_income_usd=Decimal("0.00"),
            taxable_income_usd=Decimal("0.00"),
        )
        self.assertEqual(result, Decimal("0.00"))

    def test_wage_share_allocation_matches_production(self) -> None:
        kwargs = dict(
            taxpayer_gross_wages_eur=Decimal("80000.00"),
            spouse_gross_wages_eur=Decimal("20000.00"),
            joint_wage_side_tax_eur=Decimal("25000.00"),
            eur_per_usd_yearly_average_2025=Decimal("0.886"),
        )
        self.assertEqual(
            current_year_general_foreign_tax_usd_2025(**kwargs),
            orig_wage_share(**kwargs),
        )

    def test_validate_below_ceiling_passes(self) -> None:
        # Should not raise.
        validate_documented_positive_income_denominator_bound_2025(
            total_gross_income_for_ftc_usd=Decimal("100000.00"),
            taxable_income_usd=Decimal("80000.00"),
            standard_deduction_usd=Decimal("30000.00"),
        )
        orig_validate(
            total_gross_income_for_ftc_usd=Decimal("100000.00"),
            taxable_income_usd=Decimal("80000.00"),
            standard_deduction_usd=Decimal("30000.00"),
        )


class P904HandDerivedStatuteTest(unittest.TestCase):
    """Hand-derived § 904 FTC values from statute + Form 1116 instructions.
    """

    def test_total_gross_income_sums_all_categories(self) -> None:
        # § 904(a) denominator is total gross income from all sources.
        # 100,000 + 5,000 + 250 + 100 + 250 + 0 + 750 = $106,350.
        # Authority: § 904(a); Form 1116 line 18 instructions.
        out = total_gross_income_for_ftc_2025(
            wages_usd=Decimal("100000.00"),
            ordinary_dividends_usd=Decimal("5000.00"),
            interest_income_usd=Decimal("250.00"),
            schedule_1_other_income_usd=Decimal("100.00"),
            capital_gain_distributions_usd=Decimal("250.00"),
            known_positive_short_capital_gain_usd=Decimal("0.00"),
            known_positive_long_capital_gain_usd=Decimal("750.00"),
        )
        self.assertEqual(out, Decimal("106350.00"))

    def test_standard_deduction_pro_rated_by_category_share(self) -> None:
        # Form 1116 line 3a: standard deduction allocated to category
        # by gross-income ratio. 30,000 · (90,000 / 100,000) = $27,000.
        out = standard_deduction_allocation_2025(
            standard_deduction_usd=Decimal("30000.00"),
            category_gross_income_usd=Decimal("90000.00"),
            total_gross_income_for_ftc_usd=Decimal("100000.00"),
        )
        self.assertEqual(out, Decimal("27000.0000"))

    def test_ftc_limitation_classic_3_4_share(self) -> None:
        # § 904(a): limitation = pre-credit tax × category / total.
        # 12,000 · 60,000/80,000 = $9,000.0000 (computed at 4dp via
        # the production helper's rounding contract).
        out = ftc_limitation_2025(
            regular_tax_before_credits_usd=Decimal("12000.00"),
            category_taxable_income_usd=Decimal("60000.00"),
            taxable_income_usd=Decimal("80000.00"),
        )
        self.assertEqual(out, Decimal("9000.0000"))


if __name__ == "__main__":
    unittest.main()
