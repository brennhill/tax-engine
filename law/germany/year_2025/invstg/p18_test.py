"""§ 18 InvStG 2018 numeric tests, anchored to gesetze-im-internet.de.

Authority:
- § 18 InvStG 2018 (https://www.gesetze-im-internet.de/invstg_2018/__18.html)
- BMF-Schreiben 16.01.2025 (Basiszinssatz 2025, Az. IV C 1 - S 1980-1/19/10005:008)
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.invstg.p18 import (
    BASISZINS_2025,
    VORABPAUSCHALE_BASISERTRAG_FACTOR,
)
from tax_pipeline.y2025.germany_law import (
    BASISZINS_2025 as PROD_BASISZINS,
    VORABPAUSCHALE_BASISERTRAG_FACTOR as PROD_FACTOR,
)


class P18InvStGIdentityTest(unittest.TestCase):
    def test_basisertrag_factor_matches_production(self) -> None:
        self.assertEqual(VORABPAUSCHALE_BASISERTRAG_FACTOR, PROD_FACTOR)

    def test_basiszins_2025_matches_production(self) -> None:
        self.assertEqual(BASISZINS_2025, PROD_BASISZINS)


class P18InvStGStatuteTest(unittest.TestCase):
    def test_basisertrag_factor_is_0_7(self) -> None:
        # § 18 Abs. 1 Satz 1 InvStG: 70 % of the risk-free rate.
        self.assertEqual(VORABPAUSCHALE_BASISERTRAG_FACTOR, Decimal("0.7"))

    def test_basiszins_2025_is_2_53_percent(self) -> None:
        # BMF-Schreiben 16.01.2025 (Az. IV C 1 - S 1980-1/19/10005:008).
        self.assertEqual(BASISZINS_2025, Decimal("0.0253"))


if __name__ == "__main__":
    unittest.main()
