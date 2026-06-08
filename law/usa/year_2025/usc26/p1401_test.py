"""§ 1401 SECA tax tests.

Authority:
- 26 U.S.C. § 1401 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401)
- 26 U.S.C. § 1402(a)(12) — 92.35 % factor
- IRS Schedule SE instructions (https://www.irs.gov/forms-pubs/about-schedule-se-form-1040)

Asserts identity with ``tax_pipeline.y2025.us_law.se_tax_assessment_2025``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p1401 import (
    EMPLOYEE_MEDICARE_RATE,
    MEDICARE_RATE,
    OASDI_RATE,
    SECA_NET_EARNINGS_FACTOR,
    SS_WAGE_BASE_2025_USD,
    USC_1401_URL,
    USC_1402_URL,
    se_tax_assessment_2025,
)
from tax_pipeline.y2025.us_law import (
    EMPLOYEE_MEDICARE_RATE as ORIG_EMP,
    MEDICARE_RATE as ORIG_MEDICARE,
    OASDI_RATE as ORIG_OASDI,
    SECA_NET_EARNINGS_FACTOR as ORIG_FACTOR,
    SS_WAGE_BASE_2025_USD as ORIG_BASE,
    USC_1401_URL as ORIG_1401,
    USC_1402_URL as ORIG_1402,
    USSelfEmploymentInputs2025,
    se_tax_assessment_2025 as orig_fn,
)


class P1401IdentityTest(unittest.TestCase):
    def test_urls_match_production(self) -> None:
        self.assertEqual(USC_1401_URL, ORIG_1401)
        self.assertEqual(USC_1402_URL, ORIG_1402)

    def test_constants_match_production(self) -> None:
        self.assertEqual(SECA_NET_EARNINGS_FACTOR, ORIG_FACTOR)
        self.assertEqual(OASDI_RATE, ORIG_OASDI)
        self.assertEqual(MEDICARE_RATE, ORIG_MEDICARE)
        self.assertEqual(EMPLOYEE_MEDICARE_RATE, ORIG_EMP)
        self.assertEqual(SS_WAGE_BASE_2025_USD, ORIG_BASE)

    def test_constants_have_statutory_values(self) -> None:
        # § 1402(a)(12), § 1401(a), § 1401(b)(1).
        self.assertEqual(SECA_NET_EARNINGS_FACTOR, Decimal("0.9235"))
        self.assertEqual(OASDI_RATE, Decimal("0.124"))
        self.assertEqual(MEDICARE_RATE, Decimal("0.029"))
        self.assertEqual(SS_WAGE_BASE_2025_USD, Decimal("176100"))

    def test_zero_earnings_returns_zero(self) -> None:
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("0.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=False,
        )
        shadow = se_tax_assessment_2025(se_inputs=inputs)
        prod = orig_fn(se_inputs=inputs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.se_tax_usd, Decimal("0.00"))

    def test_se_tax_below_wage_base(self) -> None:
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("50000.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=False,
        )
        shadow = se_tax_assessment_2025(se_inputs=inputs)
        prod = orig_fn(se_inputs=inputs)
        self.assertEqual(shadow, prod)

    def test_se_tax_above_wage_base(self) -> None:
        # OASDI capped at SS_WAGE_BASE_2025_USD.
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("250000.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=False,
        )
        shadow = se_tax_assessment_2025(se_inputs=inputs)
        prod = orig_fn(se_inputs=inputs)
        self.assertEqual(shadow, prod)
        # OASDI base capped at $176,100.
        self.assertEqual(
            shadow.oasdi_taxable_earnings_usd, SS_WAGE_BASE_2025_USD
        )

    def test_totalization_certificate_fails_closed(self) -> None:
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("100000.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=True,
        )
        with self.assertRaises(NotImplementedError):
            se_tax_assessment_2025(se_inputs=inputs)


class P1401HandDerivedStatuteTest(unittest.TestCase):
    """Hand-computed § 1401 SE-tax values from the statute coefficients
    and Schedule SE instructions, independent of the production module.
    """

    def test_se_tax_at_50000_net_earnings(self) -> None:
        # § 1402(a)(12): 92.35 % factor → SECA base = 50,000 · 0.9235
        # = 46,175.00. § 1401(a)+(b)(1) combined rate = 0.124 + 0.029
        # = 0.153 → SE tax = 46,175 · 0.153 = $7,064.78 (cents-rounded
        # via the Schedule SE instructions).
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("50000.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=False,
        )
        out = se_tax_assessment_2025(se_inputs=inputs)
        self.assertEqual(out.se_taxable_earnings_usd, Decimal("46175.00"))
        self.assertEqual(out.se_tax_usd, Decimal("7064.78"))

    def test_oasdi_capped_at_176100_wage_base(self) -> None:
        # § 1401(a) + § 230 SSA: SS wage base for 2025 = $176,100.
        # Net SE earnings $250,000 → SECA base = 250,000 · 0.9235 =
        # $230,875. OASDI taxable capped at $176,100 (the wage base).
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("250000.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=False,
        )
        out = se_tax_assessment_2025(se_inputs=inputs)
        self.assertEqual(
            out.oasdi_taxable_earnings_usd, Decimal("176100.00")
        )
        # OASDI portion = 176,100 · 0.124 = $21,836.40.
        self.assertEqual(
            out.oasdi_tax_usd, Decimal("21836.40")
        )

    def test_oasdi_at_100k_seca_yields_pinned_value(self) -> None:
        # § 1401(a) OASDI portion at $100K net SE: SECA base =
        # 100,000 · 0.9235 = 92,350. OASDI = 92,350 · 0.124 = $11,451.40.
        # (Below the $176,100 wage base so no cap binds.)
        inputs = USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("100000.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("100000.00"),
            totalization_certificate_present=False,
        )
        out = se_tax_assessment_2025(se_inputs=inputs)
        self.assertEqual(out.oasdi_tax_usd, Decimal("11451.40"))


if __name__ == "__main__":
    unittest.main()
