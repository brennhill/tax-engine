"""§ 1411 NIIT tests.

Authority:
- 26 U.S.C. § 1411 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411)
- IRS Form 8960 instructions (https://www.irs.gov/instructions/i8960)

Asserts identity with ``tax_pipeline.y2025.us_law.niit_assessment_2025``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p1411 import (
    NIIT_RATE,
    USC_1411_URL,
    niit_assessment_2025,
)
from tax_pipeline.y2025.us_law import (
    NIIT_RATE as ORIG_RATE,
    USC_1411_URL as ORIG_URL,
    niit_assessment_2025 as orig_fn,
)


class P1411IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_1411_URL, ORIG_URL)

    def test_rate_matches_production(self) -> None:
        self.assertEqual(NIIT_RATE, ORIG_RATE)
        self.assertEqual(NIIT_RATE, Decimal("0.038"))

    def test_below_threshold_returns_zero(self) -> None:
        kwargs = dict(
            adjusted_gross_income_usd=Decimal("180000.00"),
            capital_line_7a_usd=Decimal("0.00"),
            ordinary_dividends_usd=Decimal("5000.00"),
            interest_income_usd=Decimal("250.00"),
            substitute_payments_usd=Decimal("0.00"),
            staking_income_usd=Decimal("0.00"),
            include_staking_in_niit=False,
            niit_threshold_usd=Decimal("250000.00"),
        )
        shadow = niit_assessment_2025(**kwargs)
        prod = orig_fn(**kwargs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.niit_usd, Decimal("0.00"))

    def test_above_threshold_lesser_of_nii_and_excess(self) -> None:
        kwargs = dict(
            adjusted_gross_income_usd=Decimal("310000.00"),
            capital_line_7a_usd=Decimal("0.00"),
            ordinary_dividends_usd=Decimal("12000.00"),
            interest_income_usd=Decimal("250.00"),
            substitute_payments_usd=Decimal("0.00"),
            staking_income_usd=Decimal("0.00"),
            include_staking_in_niit=False,
            niit_threshold_usd=Decimal("250000.00"),
        )
        shadow = niit_assessment_2025(**kwargs)
        prod = orig_fn(**kwargs)
        self.assertEqual(shadow, prod)
        # NII = $12,250; excess = $60,000; lesser is $12,250 × 3.8 %.
        self.assertEqual(shadow.niit_base_usd, Decimal("12250.00"))
        self.assertEqual(shadow.niit_usd, Decimal("465.50"))

    def test_staking_inclusion_flag_matches_production(self) -> None:
        kwargs = dict(
            adjusted_gross_income_usd=Decimal("310000.00"),
            capital_line_7a_usd=Decimal("0.00"),
            ordinary_dividends_usd=Decimal("0.00"),
            interest_income_usd=Decimal("0.00"),
            substitute_payments_usd=Decimal("0.00"),
            staking_income_usd=Decimal("5000.00"),
            include_staking_in_niit=True,
            niit_threshold_usd=Decimal("250000.00"),
        )
        shadow = niit_assessment_2025(**kwargs)
        prod = orig_fn(**kwargs)
        self.assertEqual(shadow, prod)


class P1411HandDerivedStatuteTest(unittest.TestCase):
    """Numeric assertions hand-derived from § 1411 statute text +
    Form 8960 instructions, independent of the production module.
    """

    def test_niit_rate_matches_statute_3_8_percent(self) -> None:
        # § 1411(a) imposes a 3.8 % tax. Authority: 26 U.S.C. § 1411(a).
        self.assertEqual(NIIT_RATE, Decimal("0.038"))

    def test_excess_lesser_than_nii_uses_excess_as_base(self) -> None:
        # § 1411(a) base = lesser of NII and MAGI excess. With MAGI =
        # $260,000 (excess $10,000) and NII = $20,000, base = $10,000;
        # NIIT = 0.038 · 10,000 = $380.00.
        out = niit_assessment_2025(
            adjusted_gross_income_usd=Decimal("260000.00"),
            capital_line_7a_usd=Decimal("0.00"),
            ordinary_dividends_usd=Decimal("20000.00"),
            interest_income_usd=Decimal("0.00"),
            substitute_payments_usd=Decimal("0.00"),
            staking_income_usd=Decimal("0.00"),
            include_staking_in_niit=False,
            niit_threshold_usd=Decimal("250000.00"),
        )
        self.assertEqual(out.modified_agi_excess_usd, Decimal("10000.00"))
        self.assertEqual(out.niit_base_usd, Decimal("10000.00"))
        self.assertEqual(out.niit_usd, Decimal("380.00"))

    def test_capital_gain_line_7a_flows_into_nii(self) -> None:
        # § 1411(c)(1)(A)(iii): net gain attributable to property held
        # in a passive activity flows in. Form 8960 line 7a captures
        # capital-gain net income. NII = $5,000 (line 7a) + $2,000
        # (interest) = $7,000; excess = $20,000 → base = $7,000;
        # NIIT = 0.038 · 7,000 = $266.00.
        out = niit_assessment_2025(
            adjusted_gross_income_usd=Decimal("270000.00"),
            capital_line_7a_usd=Decimal("5000.00"),
            ordinary_dividends_usd=Decimal("0.00"),
            interest_income_usd=Decimal("2000.00"),
            substitute_payments_usd=Decimal("0.00"),
            staking_income_usd=Decimal("0.00"),
            include_staking_in_niit=False,
            niit_threshold_usd=Decimal("250000.00"),
        )
        self.assertEqual(out.niit_base_usd, Decimal("7000.00"))
        self.assertEqual(out.niit_usd, Decimal("266.00"))


if __name__ == "__main__":
    unittest.main()
