"""§ 3101(b)(2) Additional Medicare 0.9 % tests.

Authority:
- 26 U.S.C. § 3101 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101)
- 26 U.S.C. § 1401(b)(2)
- IRS Form 8959 (https://www.irs.gov/forms-pubs/about-form-8959)

Asserts identity with
``tax_pipeline.y2025.us_law.additional_medicare_assessment_2025``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p3101 import (
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD,
    ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD,
    ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD,
    USC_3101_URL,
    additional_medicare_assessment_2025,
)
from tax_pipeline.y2025.us_law import (
    ADDITIONAL_MEDICARE_RATE as ORIG_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD as ORIG_MFJ,
    ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD as ORIG_MFS,
    ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD as ORIG_SINGLE,
    USC_3101_URL as ORIG_URL,
    additional_medicare_assessment_2025 as orig_fn,
)


class P3101IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_3101_URL, ORIG_URL)

    def test_constants_match_production(self) -> None:
        self.assertEqual(ADDITIONAL_MEDICARE_RATE, ORIG_RATE)
        self.assertEqual(
            ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD, ORIG_SINGLE
        )
        self.assertEqual(
            ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD, ORIG_MFJ
        )
        self.assertEqual(
            ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD, ORIG_MFS
        )

    def test_constants_have_statutory_values(self) -> None:
        # § 3101(b)(2)(A)-(C).
        self.assertEqual(ADDITIONAL_MEDICARE_RATE, Decimal("0.009"))
        self.assertEqual(
            ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD, Decimal("200000")
        )
        self.assertEqual(
            ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD, Decimal("250000")
        )
        self.assertEqual(
            ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD, Decimal("125000")
        )

    def test_below_threshold_returns_zero(self) -> None:
        shadow = additional_medicare_assessment_2025(
            filing_status_label="Single",
            medicare_taxable_wages_usd=Decimal("180000.00"),
            se_taxable_earnings_usd=Decimal("0.00"),
        )
        prod = orig_fn(
            filing_status_label="Single",
            medicare_taxable_wages_usd=Decimal("180000.00"),
            se_taxable_earnings_usd=Decimal("0.00"),
        )
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.additional_medicare_tax_usd, Decimal("0.00"))

    def test_above_threshold_combined_wages_and_se(self) -> None:
        # MFJ threshold $250k; combine $200k wages + $100k SE = $300k
        # base, $50k excess × 0.9 % = $450.
        shadow = additional_medicare_assessment_2025(
            filing_status_label="Married filing jointly",
            medicare_taxable_wages_usd=Decimal("200000.00"),
            se_taxable_earnings_usd=Decimal("100000.00"),
        )
        prod = orig_fn(
            filing_status_label="Married filing jointly",
            medicare_taxable_wages_usd=Decimal("200000.00"),
            se_taxable_earnings_usd=Decimal("100000.00"),
        )
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow.additional_medicare_tax_usd, Decimal("450.00"))

    def test_unsupported_filing_status_fails_closed(self) -> None:
        with self.assertRaises(NotImplementedError):
            additional_medicare_assessment_2025(
                filing_status_label="Head of household",
                medicare_taxable_wages_usd=Decimal("100000.00"),
                se_taxable_earnings_usd=Decimal("0.00"),
            )


if __name__ == "__main__":
    unittest.main()
