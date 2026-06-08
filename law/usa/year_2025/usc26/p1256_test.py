"""§ 1256 mark-to-market 60/40 split tests.

Authority:
- 26 U.S.C. § 1256(a)(3) (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256)
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p1256 import (
    SECTION_1256_LONG_RATIO,
    SECTION_1256_SHORT_RATIO,
    USC_1256_URL,
    section_1256_split_2025,
)
from tax_pipeline.y2025.us_law import (
    SECTION_1256_LONG_RATIO as ORIG_LONG,
    SECTION_1256_SHORT_RATIO as ORIG_SHORT,
    USC_1256_URL as ORIG_URL,
    section_1256_split_2025 as orig_fn,
)


class P1256IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_1256_URL, ORIG_URL)

    def test_ratios_match_production(self) -> None:
        self.assertEqual(SECTION_1256_SHORT_RATIO, ORIG_SHORT)
        self.assertEqual(SECTION_1256_LONG_RATIO, ORIG_LONG)
        self.assertEqual(SECTION_1256_SHORT_RATIO, Decimal("0.40"))
        self.assertEqual(SECTION_1256_LONG_RATIO, Decimal("0.60"))

    def test_split_matches_production(self) -> None:
        for total in (
            Decimal("0.00"),
            Decimal("1000.00"),
            Decimal("12345.67"),
            Decimal("-5000.00"),
        ):
            self.assertEqual(
                section_1256_split_2025(total),
                orig_fn(total),
                msg=f"total={total}",
            )

    def test_split_60_40(self) -> None:
        # § 1256(a)(3) — 40% short, 60% long.
        short, long_ = section_1256_split_2025(Decimal("1000.00"))
        self.assertEqual(short, Decimal("400.00"))
        self.assertEqual(long_, Decimal("600.00"))


if __name__ == "__main__":
    unittest.main()
