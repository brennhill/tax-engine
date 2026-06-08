"""§ 22 Nr. 3 EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 22 Nr. 3 Satz 2 EStG
(https://www.gesetze-im-internet.de/estg/__22.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p22 import (
    OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR,
    other_income_22nr3_taxable_2025,
)
from tax_pipeline.y2025.germany_law import (
    OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR as PROD_FG,
    other_income_22nr3_taxable_2025 as prod_fn,
)


class P22EstgIdentityTest(unittest.TestCase):
    def test_freigrenze_matches_production(self) -> None:
        self.assertEqual(OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR, PROD_FG)

    def test_below_threshold_matches_production(self) -> None:
        s = other_income_22nr3_taxable_2025(
            Decimal("200.00"), OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR
        )
        p = prod_fn(Decimal("200.00"), PROD_FG)
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("0.00"))

    def test_at_threshold_matches_production(self) -> None:
        s = other_income_22nr3_taxable_2025(
            Decimal("256.00"), OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR
        )
        p = prod_fn(Decimal("256.00"), PROD_FG)
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("256.00"))

    def test_above_threshold_matches_production(self) -> None:
        s = other_income_22nr3_taxable_2025(
            Decimal("500.00"), OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR
        )
        p = prod_fn(Decimal("500.00"), PROD_FG)
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("500.00"))


class P22EstgStatuteTest(unittest.TestCase):
    def test_freigrenze_is_256_eur(self) -> None:
        # § 22 Nr. 3 Satz 2 EStG.
        self.assertEqual(OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR, Decimal("256.00"))

    def test_negative_input_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            other_income_22nr3_taxable_2025(
                Decimal("-1.00"), OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR
            )


if __name__ == "__main__":
    unittest.main()
