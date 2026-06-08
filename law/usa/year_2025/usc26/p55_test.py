"""§ 55 AMT tests, anchored to Cornell uscode.

Authority:
- 26 U.S.C. § 55 (https://www.law.cornell.edu/uscode/text/26/55)
- 26 U.S.C. § 1(h) — preferential rates preserved by § 55(b)(3)
- Rev. Proc. 2024-40 (https://www.irs.gov/pub/irs-drop/rp-24-40.pdf)
- IRS Form 6251 (https://www.irs.gov/forms-pubs/about-form-6251)

Asserts identity with the production module's § 55 helper chain.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p55 import (
    AMT_PHASEOUT_RATE,
    AMT_RATE_HIGH,
    AMT_RATE_LOW,
    USC_55_URL,
    amt_exemption_after_phaseout_2025,
    amt_owed_2025,
    amt_tentative_minimum_tax_2025,
)
from tax_pipeline.y2025.us_law import (
    AMT_PHASEOUT_RATE as ORIG_PHASEOUT,
    AMT_RATE_HIGH as ORIG_HIGH,
    AMT_RATE_LOW as ORIG_LOW,
    USC_55_URL as ORIG_URL,
    USTaxConstants2025,
    amt_exemption_after_phaseout_2025 as orig_exemption,
    amt_owed_2025 as orig_owed,
    amt_tentative_minimum_tax_2025 as orig_tentative,
)


def _mfj_constants_2025() -> USTaxConstants2025:
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


class P55IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_55_URL, ORIG_URL)

    def test_constants_match_production(self) -> None:
        self.assertEqual(AMT_PHASEOUT_RATE, ORIG_PHASEOUT)
        self.assertEqual(AMT_RATE_LOW, ORIG_LOW)
        self.assertEqual(AMT_RATE_HIGH, ORIG_HIGH)

    def test_constants_have_statutory_values(self) -> None:
        self.assertEqual(AMT_PHASEOUT_RATE, Decimal("0.25"))
        self.assertEqual(AMT_RATE_LOW, Decimal("0.26"))
        self.assertEqual(AMT_RATE_HIGH, Decimal("0.28"))

    def test_exemption_below_threshold_full(self) -> None:
        # MFJ exemption $137,000; AMTI $500,000 < $1,252,700 phase-out start.
        kwargs = dict(
            amti_usd=Decimal("500000.00"),
            filing_status_label="Married filing jointly",
        )
        shadow = amt_exemption_after_phaseout_2025(**kwargs)
        prod = orig_exemption(**kwargs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow, Decimal("137000.00"))

    def test_exemption_above_threshold_phased_out(self) -> None:
        # MFJ exemption phases out at $0.25/$1.00 above $1,252,700.
        kwargs = dict(
            amti_usd=Decimal("1500000.00"),
            filing_status_label="Married filing jointly",
        )
        shadow = amt_exemption_after_phaseout_2025(**kwargs)
        prod = orig_exemption(**kwargs)
        self.assertEqual(shadow, prod)

    def test_tentative_min_tax_below_break(self) -> None:
        # AMTI excess $100k, MFJ rate-break $232,600 → all at 26 %.
        kwargs = dict(
            amti_after_exemption_usd=Decimal("100000.00"),
            preferential_amti_usd=Decimal("0.00"),
            filing_status_label="Married filing jointly",
            constants=_mfj_constants_2025(),
        )
        shadow = amt_tentative_minimum_tax_2025(**kwargs)
        prod = orig_tentative(**kwargs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow, Decimal("26000.00"))

    def test_tentative_min_tax_above_break(self) -> None:
        kwargs = dict(
            amti_after_exemption_usd=Decimal("500000.00"),
            preferential_amti_usd=Decimal("0.00"),
            filing_status_label="Married filing jointly",
            constants=_mfj_constants_2025(),
        )
        shadow = amt_tentative_minimum_tax_2025(**kwargs)
        prod = orig_tentative(**kwargs)
        self.assertEqual(shadow, prod)

    def test_amt_owed_when_tentative_above_regular(self) -> None:
        kwargs = dict(
            tentative_min_tax_usd=Decimal("50000.00"),
            amtftc_usd=Decimal("5000.00"),
            regular_tax_after_ftc_usd=Decimal("30000.00"),
        )
        shadow = amt_owed_2025(**kwargs)
        prod = orig_owed(**kwargs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow, Decimal("15000.00"))

    def test_amt_owed_when_regular_dominates(self) -> None:
        kwargs = dict(
            tentative_min_tax_usd=Decimal("10000.00"),
            amtftc_usd=Decimal("0.00"),
            regular_tax_after_ftc_usd=Decimal("40000.00"),
        )
        shadow = amt_owed_2025(**kwargs)
        prod = orig_owed(**kwargs)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow, Decimal("0.00"))

    def test_unsupported_filing_status_fails_closed(self) -> None:
        with self.assertRaises(NotImplementedError):
            amt_exemption_after_phaseout_2025(
                amti_usd=Decimal("100000.00"),
                filing_status_label="Head of household",
            )


class P55HandDerivedStatuteTest(unittest.TestCase):
    """Numeric assertions hand-derived from § 55 + Rev. Proc. 2024-40
    § 3.11. Independent of the production module so a regression in
    either side is caught by the absolute value, not just by a
    shadow-equals-prod comparison.
    """

    def test_mfj_exemption_phaseout_at_known_amti(self) -> None:
        # § 55(d)(3): MFJ AMTI = $1,500,000 → reduction =
        # ($1,500,000 − $1,252,700) · 0.25 = $61,825 → exemption =
        # $137,000 − $61,825 = $75,175. Authority: Rev. Proc. 2024-40
        # § 3.11; § 55(d)(3).
        out = amt_exemption_after_phaseout_2025(
            amti_usd=Decimal("1500000.00"),
            filing_status_label="Married filing jointly",
        )
        self.assertEqual(out, Decimal("75175.00"))

    def test_mfj_tentative_above_break_pinned(self) -> None:
        # AMT_RATE_BREAK_MFJ_2025 = $239,100 (per Rev. Proc. 2024-40
        # § 3.11). With AMTI excess $500,000:
        #   low band: $239,100 · 0.26 = $62,166.00
        #   high band: ($500,000 − $239,100) · 0.28 = $73,052.00
        #   total = $135,218.00.
        out = amt_tentative_minimum_tax_2025(
            amti_after_exemption_usd=Decimal("500000.00"),
            preferential_amti_usd=Decimal("0.00"),
            filing_status_label="Married filing jointly",
            constants=_mfj_constants_2025(),
        )
        self.assertEqual(out, Decimal("135218.00"))

    def test_amtftc_reduces_amt_owed_dollar_for_dollar(self) -> None:
        # § 55(a): AMT = max(0, tentative − AMTFTC − regular_after_ftc).
        # tentative $50K − AMTFTC $20K − regular $25K = $5,000.
        out = amt_owed_2025(
            tentative_min_tax_usd=Decimal("50000.00"),
            amtftc_usd=Decimal("20000.00"),
            regular_tax_after_ftc_usd=Decimal("25000.00"),
        )
        self.assertEqual(out, Decimal("5000.00"))


if __name__ == "__main__":
    unittest.main()
