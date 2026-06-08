"""§ 1211 capital-loss-limit tests.

Authority:
- 26 U.S.C. § 1211 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211)
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p1211 import (
    MFS_CAPITAL_LOSS_LIMIT_USD,
    STANDARD_CAPITAL_LOSS_LIMIT_USD,
    USC_1211_URL,
)
from tax_pipeline.y2025.us_law import (
    MFS_CAPITAL_LOSS_LIMIT_USD as ORIG_MFS,
    STANDARD_CAPITAL_LOSS_LIMIT_USD as ORIG_STD,
    USC_1211_URL as ORIG_URL,
)


class P1211IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_1211_URL, ORIG_URL)

    def test_standard_limit_matches_production(self) -> None:
        self.assertEqual(STANDARD_CAPITAL_LOSS_LIMIT_USD, ORIG_STD)
        self.assertEqual(STANDARD_CAPITAL_LOSS_LIMIT_USD, Decimal("3000.00"))

    def test_mfs_limit_matches_production(self) -> None:
        self.assertEqual(MFS_CAPITAL_LOSS_LIMIT_USD, ORIG_MFS)
        self.assertEqual(MFS_CAPITAL_LOSS_LIMIT_USD, Decimal("1500.00"))

    def test_mfs_is_half_of_standard(self) -> None:
        # § 1211(b)(2): MFS limit is half.
        self.assertEqual(
            MFS_CAPITAL_LOSS_LIMIT_USD * Decimal(2),
            STANDARD_CAPITAL_LOSS_LIMIT_USD,
        )


if __name__ == "__main__":
    unittest.main()
