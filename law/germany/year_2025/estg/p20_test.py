"""§ 20 EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 20 EStG (https://www.gesetze-im-internet.de/estg/__20.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p20 import (
    SAVER_ALLOWANCE_JOINT_2025_EUR,
    SAVER_ALLOWANCE_SINGLE_2025_EUR,
    saver_allowance_for_spouse_20_9_2025,
)
from tax_pipeline.y2025.germany_law import (
    SAVER_ALLOWANCE_JOINT_2025_EUR as PROD_JOINT,
    SAVER_ALLOWANCE_SINGLE_2025_EUR as PROD_SINGLE,
    saver_allowance_for_spouse_20_9_2025 as prod_fn,
)


class P20EstgIdentityTest(unittest.TestCase):
    def test_joint_allowance_matches_production(self) -> None:
        self.assertEqual(SAVER_ALLOWANCE_JOINT_2025_EUR, PROD_JOINT)

    def test_single_allowance_matches_production(self) -> None:
        self.assertEqual(SAVER_ALLOWANCE_SINGLE_2025_EUR, PROD_SINGLE)

    def test_function_matches_production_basic_split(self) -> None:
        # Each spouse has €600 capital → both use €600 of the half-€1,000 each.
        s = saver_allowance_for_spouse_20_9_2025(
            Decimal("600.00"), Decimal("600.00"), Decimal("2000.00")
        )
        p = prod_fn(Decimal("600.00"), Decimal("600.00"), Decimal("2000.00"))
        self.assertEqual(s, p)

    def test_function_matches_production_transfer_excess(self) -> None:
        # Spouse A has €1,500 capital, spouse B has €100 → unused €900 transfers.
        s = saver_allowance_for_spouse_20_9_2025(
            Decimal("1500.00"), Decimal("100.00"), Decimal("2000.00")
        )
        p = prod_fn(Decimal("1500.00"), Decimal("100.00"), Decimal("2000.00"))
        self.assertEqual(s, p)


class P20EstgStatuteTest(unittest.TestCase):
    def test_single_is_1000_eur(self) -> None:
        # § 20 Abs. 9 Satz 1 EStG.
        self.assertEqual(SAVER_ALLOWANCE_SINGLE_2025_EUR, Decimal("1000.00"))

    def test_joint_is_2000_eur(self) -> None:
        # § 20 Abs. 9 Satz 2 EStG.
        self.assertEqual(SAVER_ALLOWANCE_JOINT_2025_EUR, Decimal("2000.00"))

    def test_per_spouse_default_half(self) -> None:
        # When both spouses use their own bucket, neither can exceed €1,000.
        result = saver_allowance_for_spouse_20_9_2025(
            Decimal("5000.00"), Decimal("5000.00"), Decimal("2000.00")
        )
        self.assertEqual(result, Decimal("1000.00"))


if __name__ == "__main__":
    unittest.main()
