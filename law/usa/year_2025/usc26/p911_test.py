"""§ 911 FEIE / housing exclusion / housing deduction tests.

Authority:
- 26 U.S.C. § 911 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911)
- Rev. Proc. 2024-40 § 3.34 (https://www.irs.gov/pub/irs-drop/rp-24-40.pdf)
- IRS Form 2555 (https://www.irs.gov/forms-pubs/about-form-2555)
- IRS Pub. 54 (https://www.irs.gov/publications/p54)

Asserts identity with ``tax_pipeline.y2025.us_law.feie_assessment_2025``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p911 import (
    SECTION_911_FEIE_2025_USD,
    SECTION_911_HOUSING_BASE_RATE,
    SECTION_911_HOUSING_CEILING_RATE,
    USC_911_URL,
    feie_assessment_2025,
)
from tax_pipeline.y2025.us_law import (
    SECTION_911_FEIE_2025_USD as ORIG_FEIE,
    SECTION_911_HOUSING_BASE_RATE as ORIG_BASE,
    SECTION_911_HOUSING_CEILING_RATE as ORIG_CEIL,
    USC_911_URL as ORIG_URL,
    USFEIEInputs2025,
    feie_assessment_2025 as orig_fn,
)


class P911IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_911_URL, ORIG_URL)

    def test_constants_match_production(self) -> None:
        self.assertEqual(SECTION_911_FEIE_2025_USD, ORIG_FEIE)
        self.assertEqual(SECTION_911_HOUSING_BASE_RATE, ORIG_BASE)
        self.assertEqual(SECTION_911_HOUSING_CEILING_RATE, ORIG_CEIL)

    def test_housing_rates_are_statutory(self) -> None:
        # § 911(c)(1)(B) and § 911(c)(2)(A).
        self.assertEqual(SECTION_911_HOUSING_BASE_RATE, Decimal("0.16"))
        self.assertEqual(SECTION_911_HOUSING_CEILING_RATE, Decimal("0.30"))

    def test_not_elected_returns_zero(self) -> None:
        inputs = USFEIEInputs2025(
            elected=False,
            foreign_earned_income_usd=Decimal("0.00"),
            qualifying_test="",
            housing_expenses_usd=Decimal("0.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
        shadow = feie_assessment_2025(feie_inputs=inputs)
        prod = orig_fn(feie_inputs=inputs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.excluded_amount_usd, Decimal("0.00"))

    def test_elected_below_ceiling_matches_production(self) -> None:
        inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal("90000.00"),
            qualifying_test="bona_fide_residence",
            housing_expenses_usd=Decimal("30000.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("12000.00"),
        )
        shadow = feie_assessment_2025(feie_inputs=inputs)
        prod = orig_fn(feie_inputs=inputs)
        self.assertEqual(shadow, prod)

    def test_elected_above_ceiling_caps_at_130k(self) -> None:
        inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal("250000.00"),
            qualifying_test="physical_presence",
            housing_expenses_usd=Decimal("50000.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
        shadow = feie_assessment_2025(feie_inputs=inputs)
        prod = orig_fn(feie_inputs=inputs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.excluded_amount_usd, Decimal("130000.00"))

    def test_self_employed_routes_to_deduction(self) -> None:
        inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal("180000.00"),
            qualifying_test="bona_fide_residence",
            housing_expenses_usd=Decimal("40000.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=True,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
        shadow = feie_assessment_2025(feie_inputs=inputs)
        prod = orig_fn(feie_inputs=inputs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.housing_exclusion_usd, Decimal("0.00"))
        self.assertGreater(shadow.housing_deduction_usd, Decimal("0.00"))

    def test_invalid_qualifying_test_fails_closed(self) -> None:
        inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal("90000.00"),
            qualifying_test="invalid",
            housing_expenses_usd=Decimal("0.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
        with self.assertRaises(ValueError):
            feie_assessment_2025(feie_inputs=inputs)


class P911HandDerivedStatuteTest(unittest.TestCase):
    """Numeric assertions derived from § 911 statute text + Rev. Proc.
    2024-40 § 3.34 — independent of the production module so a
    regression in either side is caught by the absolute value, not
    just by a shadow-equals-prod comparison.
    """

    def test_2025_feie_ceiling_is_130000(self) -> None:
        # Authority: Rev. Proc. 2024-40 § 3.34. The 2025 § 911(b)(2)(D)
        # exclusion ceiling is $130,000.
        self.assertEqual(SECTION_911_FEIE_2025_USD, Decimal("130000"))

    def test_housing_base_amount_is_20800_at_2025_feie(self) -> None:
        # § 911(c)(1)(B): base = 16 % × FEIE = 0.16 · 130,000 = $20,800.
        # Authority: 26 U.S.C. § 911(c)(1)(B).
        self.assertEqual(
            SECTION_911_FEIE_2025_USD * SECTION_911_HOUSING_BASE_RATE,
            Decimal("20800.00"),
        )

    def test_statutory_housing_ceiling_is_39000_at_2025_feie(self) -> None:
        # § 911(c)(2)(A): default ceiling = 30 % × FEIE = 0.30 · 130,000
        # = $39,000.  Authority: 26 U.S.C. § 911(c)(2)(A).
        self.assertEqual(
            SECTION_911_FEIE_2025_USD * SECTION_911_HOUSING_CEILING_RATE,
            Decimal("39000.00"),
        )

    def test_below_base_yields_zero_housing_amount(self) -> None:
        # § 911(c)(1)(B): housing_amount = max(0, expenses − base).
        # Below base → zero. Authority: 26 U.S.C. § 911(c)(1)(B).
        inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal("100000.00"),
            qualifying_test="physical_presence",
            housing_expenses_usd=Decimal("18000.00"),  # below $20,800 base
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
        out = feie_assessment_2025(feie_inputs=inputs)
        self.assertEqual(out.housing_exclusion_usd, Decimal("0.00"))

    def test_at_ceiling_housing_exclusion_is_18200(self) -> None:
        # § 911(c)(1)(B) + (c)(2)(A): expenses = ceiling = 39,000 →
        # housing_amount = 39,000 − 20,800 = $18,200.
        inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal("200000.00"),
            qualifying_test="bona_fide_residence",
            housing_expenses_usd=Decimal("39000.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
        out = feie_assessment_2025(feie_inputs=inputs)
        self.assertEqual(out.housing_exclusion_usd, Decimal("18200.00"))


if __name__ == "__main__":
    unittest.main()
