"""§ 911(c)(2)(A) housing exclusion at the exact 30 %-of-FEIE ceiling.

Authority: 26 U.S.C. § 911(c)(2)(A) — qualifying housing expenses are
limited to the § 911(c)(2)(A) ceiling, which equals 30 % of the
§ 911(b)(2)(D) FEIE ceiling unless the taxpayer is in a
location-adjusted high-cost area (IRS Notice 2024-77).

For 2025 (Rev. Proc. 2024-40 § 3.34)::

    FEIE ceiling = $130,000
    statutory housing ceiling = 0.30 · 130,000 = $39,000
    statutory housing base    = 0.16 · 130,000 = $20,800
    housing amount = max(0, min(expenses, ceiling) − base)

URL: https://www.law.cornell.edu/uscode/text/26/911
URL: https://www.irs.gov/pub/irs-drop/n-24-77.pdf

This test pins behaviour at exactly ``housing_expenses == cap_amount``
and at ``cap_amount + $0.01``: the cap acts as a saturation, so the
two cases must yield the same housing exclusion (€18,200).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.rev_proc.proc_2024_40.p3_34 import (
    SECTION_911_FEIE_2025_USD,
)
from law.usa.year_2025.usc26.p911 import (
    SECTION_911_HOUSING_BASE_RATE,
    SECTION_911_HOUSING_CEILING_RATE,
    feie_assessment_2025,
)
from tax_pipeline.y2025.us_law import USFEIEInputs2025


def _inputs(*, housing_expenses: Decimal) -> USFEIEInputs2025:
    return USFEIEInputs2025(
        elected=True,
        foreign_earned_income_usd=Decimal("200000.00"),
        qualifying_test="physical_presence",
        housing_expenses_usd=housing_expenses,
        location_adjusted_housing_ceiling_usd=None,
        self_employed=False,
        foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
    )


class P911HousingAtCeilingTest(unittest.TestCase):
    """§ 911(c)(2)(A) cap saturates at exactly cap_amount, and the same
    saturation persists one cent above.
    """

    def test_2025_constants_match_statute(self) -> None:
        # Sanity-check the inflation-adjusted constants against the
        # task-specified worked example.
        self.assertEqual(SECTION_911_FEIE_2025_USD, Decimal("130000"))
        self.assertEqual(SECTION_911_HOUSING_CEILING_RATE, Decimal("0.30"))
        self.assertEqual(SECTION_911_HOUSING_BASE_RATE, Decimal("0.16"))
        cap = SECTION_911_FEIE_2025_USD * SECTION_911_HOUSING_CEILING_RATE
        self.assertEqual(cap, Decimal("39000.00"))
        base = SECTION_911_FEIE_2025_USD * SECTION_911_HOUSING_BASE_RATE
        self.assertEqual(base, Decimal("20800.00"))

    def test_housing_exclusion_boundary_matrix(self) -> None:
        # § 911(c)(1)(B) base + § 911(c)(2)(A) cap. ``housing_amount =
        # max(0, min(expenses, cap) − base)``. Each row pins one
        # boundary so the saturation behaviour is exercised at the
        # cents.
        cases = (
            # § 911(c)(1)(B): expenses ≤ base → exclusion 0.
            (Decimal("20800.00"), Decimal("0.00"), "exactly at base"),
            # +0.01 above base → +$0.01 exclusion.
            (Decimal("20800.01"), Decimal("0.01"), "+0.01 above base"),
            # § 911(c)(2)(A): exactly at cap → 39000 − 20800 = 18200.
            (Decimal("39000.00"), Decimal("18200.00"), "exactly at cap"),
            # +0.01 above cap → cap binds; same exclusion.
            (Decimal("39000.01"), Decimal("18200.00"), "+0.01 above cap saturates"),
            # Far above cap still saturates.
            (Decimal("100000.00"), Decimal("18200.00"), "far above cap saturates"),
        )
        for housing_expenses, expected_exclusion, note in cases:
            with self.subTest(housing_expenses=housing_expenses, note=note):
                out = feie_assessment_2025(
                    feie_inputs=_inputs(housing_expenses=housing_expenses)
                )
                self.assertEqual(out.housing_exclusion_usd, expected_exclusion)


if __name__ == "__main__":
    unittest.main()
