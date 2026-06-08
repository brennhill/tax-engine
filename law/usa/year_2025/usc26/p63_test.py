"""§ 63 taxable-income subtraction tests.

Authority:
- 26 U.S.C. § 63(b) (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63)

Asserts identity with ``tax_pipeline.y2025.us_law.taxable_income_2025``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p63 import USC_63_URL, taxable_income_2025
from tax_pipeline.y2025.us_law import (
    USC_63_URL as ORIG_URL,
    taxable_income_2025 as orig_fn,
)


class P63IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_63_URL, ORIG_URL)

    def test_subtraction_matches_production(self) -> None:
        agi = Decimal("100000.00")
        std = Decimal("15000.00")
        self.assertEqual(taxable_income_2025(agi, std), orig_fn(agi, std))
        self.assertEqual(taxable_income_2025(agi, std), Decimal("85000.00"))

    def test_negative_floored_to_zero(self) -> None:
        # § 63(b): no negative taxable income; floor at zero.
        result = taxable_income_2025(Decimal("5000.00"), Decimal("15000.00"))
        self.assertEqual(result, Decimal("0.00"))

    def test_zero_agi_yields_zero(self) -> None:
        self.assertEqual(
            taxable_income_2025(Decimal("0.00"), Decimal("15000.00")),
            Decimal("0.00"),
        )


if __name__ == "__main__":
    unittest.main()
