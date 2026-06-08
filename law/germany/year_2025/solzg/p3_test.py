"""§ 3 SolzG 1995 numeric tests, anchored to gesetze-im-internet.de.

Authority: § 3 SolzG 1995 (assessment base) paired with § 4 Satz 1
SolzG 1995 (5,5 % rate).
- https://www.gesetze-im-internet.de/solzg_1995/__3.html
- https://www.gesetze-im-internet.de/solzg_1995/__4.html
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.solzg.p3 import SOLI_RATE
from tax_pipeline.y2025.germany_law import SOLI_RATE as PROD_SOLI_RATE


class P3SolzgIdentityTest(unittest.TestCase):
    def test_soli_rate_matches_production(self) -> None:
        self.assertEqual(SOLI_RATE, PROD_SOLI_RATE)


class P3SolzgStatuteTest(unittest.TestCase):
    def test_soli_rate_is_5_5_percent(self) -> None:
        # § 4 Satz 1 SolzG 1995 paired with § 3 base.
        self.assertEqual(SOLI_RATE, Decimal("0.055"))


if __name__ == "__main__":
    unittest.main()
