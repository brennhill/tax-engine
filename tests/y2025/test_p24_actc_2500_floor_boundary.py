"""§ 24(d)(1)(B)(i) ACTC at the exact $2,500 earned-income floor.

Authority: 26 U.S.C. § 24(d)(1)(B)(i) — refundable Additional Child
Tax Credit (ACTC) is 15 % of (earned income − $2,500), floored at zero,
capped at $1,700 per qualifying child (Rev. Proc. 2024-40 § 3.05).

URL: https://www.law.cornell.edu/uscode/text/26/24
URL: https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
URL: https://www.irs.gov/pub/irs-drop/rp-24-40.pdf

This test pins behaviour AT and JUST PAST the $2,500 floor — the
"first dollar of refundability" boundary that a regression in the
floor comparison (``<`` vs ``<=``) would silently shift.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p24 import ctc_and_odc_assessment_2025


def _kwargs(earned_income: Decimal) -> dict:
    return dict(
        children_count_qualifying_for_ctc=1,
        children_count_qualifying_for_odc=0,
        earned_income_usd=earned_income,
        modified_agi_usd=earned_income,
        regular_tax_after_ftc_usd=Decimal("0"),
        filing_status_label="Single",
    )


class P24ActcFloorBoundaryTest(unittest.TestCase):
    """Pin the refundable ACTC value at exact $2,500 and at the
    smallest amount above the floor.
    """

    def test_actc_floor_around_2500_and_15_percent_phase_in(self) -> None:
        # § 24(d)(1)(B)(i): refundable ACTC = round_cents(0.15 ×
        # max(0, earned_income − 2500)). The boundary cases pin the
        # floor (excess clamped to 0) and the cents-rounding behavior.
        cases = (
            (Decimal("1000.00"), Decimal("0.00"), "below floor → clamp to 0"),
            (Decimal("2500.00"), Decimal("0.00"), "at floor: excess = 0"),
            (Decimal("2500.01"), Decimal("0.00"), "+0.01: 0.0015 rounds to 0"),
            (Decimal("2503.34"), Decimal("0.50"), "first cent of real phase-in"),
            (Decimal("3000.00"), Decimal("75.00"), "CLAUDE.md worked example"),
        )
        for earned, expected, note in cases:
            with self.subTest(earned=earned, note=note):
                out = ctc_and_odc_assessment_2025(**_kwargs(earned))
                self.assertEqual(out.refundable_actc_usd, expected)


if __name__ == "__main__":
    unittest.main()
