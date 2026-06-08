"""§ 1411(a)/(b) NIIT at the exact MAGI threshold boundaries.

Authority: 26 U.S.C. § 1411(a) — 3.8 % NIIT on the lesser of net
investment income and the MAGI excess over a filing-status threshold.
26 U.S.C. § 1411(b) — statutory thresholds: Single $200,000; MFJ
$250,000; MFS $125,000.
26 U.S.C. § 1411(d)(1)(A) — § 911 excluded foreign earned income is
added back to MAGI for NIIT purposes (FEIE elections do NOT shrink the
NIIT base).

URL: https://www.law.cornell.edu/uscode/text/26/1411
URL: https://www.irs.gov/instructions/i8960

These tests pin behaviour AT the exact threshold (excess = 0 → NIIT 0)
and at one cent above (excess = $0.01 → NIIT base = $0.01 → 0.038 ·
0.01 = $0.00038 → cents rounding → $0.00). They guard the
``modified_agi_excess = max(0, MAGI − threshold)`` clamp.

A separate test pins the MFS threshold ($125,000) when FEIE is
elected — § 1411(d)(1)(A) requires the § 911 excluded amount to be
added back to MAGI BEFORE the threshold comparison, but the threshold
itself is NOT modified by the FEIE election.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p1411 import niit_assessment_2025


def _kwargs(magi: Decimal, *, threshold: Decimal, nii: Decimal) -> dict:
    # Concentrate net investment income into ``ordinary_dividends_usd``
    # so the NII parameter is unambiguous; the other line items are
    # zero so the test surface is the threshold-comparison logic.
    return dict(
        adjusted_gross_income_usd=magi,
        capital_line_7a_usd=Decimal("0.00"),
        ordinary_dividends_usd=nii,
        interest_income_usd=Decimal("0.00"),
        substitute_payments_usd=Decimal("0.00"),
        staking_income_usd=Decimal("0.00"),
        include_staking_in_niit=False,
        niit_threshold_usd=threshold,
    )


class P1411ThresholdBoundarySingleTest(unittest.TestCase):
    """Single filer at exactly the $200,000 § 1411(b) threshold."""

    def test_threshold_clamp_at_and_around_200000(self) -> None:
        # § 1411(a)/(b) MAGI-excess clamp at the single-filer threshold.
        # NII = $50,000 in every row so the clamp posture is what's
        # exercised, not the NII branch.
        cases = (
            (Decimal("199999.99"), Decimal("0.00"), Decimal("0.00"),
             "below threshold → excess clamped to 0"),
            (Decimal("200000.00"), Decimal("0.00"), Decimal("0.00"),
             "exactly at threshold → niit 0"),
            (Decimal("200000.01"), Decimal("0.01"), Decimal("0.00"),
             "+ 1 cent → excess 0.01; 0.038 cents rounds to 0"),
        )
        for magi, expected_excess, expected_niit, note in cases:
            with self.subTest(magi=magi, note=note):
                out = niit_assessment_2025(
                    **_kwargs(
                        magi,
                        threshold=Decimal("200000.00"),
                        nii=Decimal("50000.00"),
                    )
                )
                self.assertEqual(out.modified_agi_excess_usd, expected_excess)
                self.assertEqual(out.niit_usd, expected_niit)


class P1411ThresholdMfsWithFeieTest(unittest.TestCase):
    """MFS + FEIE elected: threshold remains $125,000 per § 1411(b).

    § 1411(d)(1)(A) requires the § 911-excluded foreign earned income
    to be added back to MAGI BEFORE the threshold comparison. The
    threshold itself is set by filing status (§ 1411(b)) and is NOT
    modified by the FEIE election. This test pins the MFS threshold
    at the $125,000 level even when the caller has already added back
    the FEIE excluded amount upstream (the
    ``adjusted_gross_income_usd`` parameter is documented as MAGI per
    F-USLAW-5).
    """

    def test_mfs_threshold_125_000_at_exact_boundary_niit_zero(self) -> None:
        # § 1411(b): MFS threshold is $125,000. MAGI = 125,000 (e.g.,
        # $100,000 unrelated AGI + $25,000 § 911 add-back) → NIIT 0.
        out = niit_assessment_2025(
            **_kwargs(
                Decimal("125000.00"),
                threshold=Decimal("125000.00"),
                nii=Decimal("10000.00"),
            )
        )
        self.assertEqual(out.modified_agi_excess_usd, Decimal("0.00"))
        self.assertEqual(out.niit_usd, Decimal("0.00"))

    def test_mfs_threshold_125_000_above_boundary_with_feie_addback(self) -> None:
        # MAGI 130,000 (raw AGI 100,000 + § 1411(d)(1)(A) FEIE add-back
        # 30,000). Excess = 5,000. NII = 4,000 → niit_base = 4,000.
        # NIIT = 4,000 · 0.038 = $152.00.
        out = niit_assessment_2025(
            **_kwargs(
                Decimal("130000.00"),
                threshold=Decimal("125000.00"),
                nii=Decimal("4000.00"),
            )
        )
        self.assertEqual(out.modified_agi_excess_usd, Decimal("5000.00"))
        self.assertEqual(out.niit_base_usd, Decimal("4000.00"))
        self.assertEqual(out.niit_usd, Decimal("152.00"))


if __name__ == "__main__":
    unittest.main()
