"""§ 32d EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 32d EStG (https://www.gesetze-im-internet.de/estg/__32d.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p32d import (
    CAPITAL_TAX_RATE_2025,
    GUENSTIGERPRUEFUNG_MATERIALITY_EUR,
    capital_tax_after_foreign_tax_credit_2025,
    foreign_tax_credit_32d5_cap_2025,
    treaty_relieved_capital_tax_2025,
)
from tax_pipeline.y2025.germany_law import (
    CAPITAL_TAX_RATE_2025 as PROD_RATE,
    GUENSTIGERPRUEFUNG_MATERIALITY_EUR as PROD_MAT,
    capital_tax_after_foreign_tax_credit_2025 as prod_capital_tax,
    foreign_tax_credit_32d5_cap_2025 as prod_ftc,
    treaty_relieved_capital_tax_2025 as prod_treaty,
)


class P32dEstgIdentityTest(unittest.TestCase):
    def test_capital_tax_rate_matches_production(self) -> None:
        self.assertEqual(CAPITAL_TAX_RATE_2025, PROD_RATE)

    def test_guenstigerpruefung_threshold_matches_production(self) -> None:
        self.assertEqual(GUENSTIGERPRUEFUNG_MATERIALITY_EUR, PROD_MAT)

    def test_ftc_cap_matches_production(self) -> None:
        items = (
            (Decimal("1000.00"), Decimal("200.00"), Decimal("0.00")),
            (Decimal("500.00"), Decimal("200.00"), Decimal("50.00")),
        )
        s = foreign_tax_credit_32d5_cap_2025(items, capital_tax_rate=CAPITAL_TAX_RATE_2025)
        p = prod_ftc(items, capital_tax_rate=PROD_RATE)
        self.assertEqual(s, p)

    def test_capital_tax_assessment_matches_production(self) -> None:
        s = capital_tax_after_foreign_tax_credit_2025(
            Decimal("10000.00"),
            Decimal("100.00"),
            capital_tax_rate=CAPITAL_TAX_RATE_2025,
            soli_rate=Decimal("0.055"),
        )
        p = prod_capital_tax(
            Decimal("10000.00"),
            Decimal("100.00"),
            capital_tax_rate=PROD_RATE,
            soli_rate=Decimal("0.055"),
        )
        self.assertEqual(s.taxable_capital_eur, p.taxable_capital_eur)
        self.assertEqual(s.gross_income_tax_eur, p.gross_income_tax_eur)
        self.assertEqual(s.foreign_tax_credit_eur, p.foreign_tax_credit_eur)
        self.assertEqual(s.total_tax_eur, p.total_tax_eur)

    def test_treaty_zero_credit_matches_production(self) -> None:
        s = treaty_relieved_capital_tax_2025(
            Decimal("1000.00"), Decimal("55.00"), Decimal("0.00")
        )
        p = prod_treaty(Decimal("1000.00"), Decimal("55.00"), Decimal("0.00"))
        self.assertEqual(s.total_tax_after_treaty_eur, p.total_tax_after_treaty_eur)


class P32dEstgStatuteTest(unittest.TestCase):
    def test_capital_tax_rate_is_25_percent(self) -> None:
        # § 32d Abs. 1 Satz 1 EStG.
        self.assertEqual(CAPITAL_TAX_RATE_2025, Decimal("0.25"))

    def test_ftc_cap_below_item_cap(self) -> None:
        # Foreign tax €200 on €1,000 income at 25% → cap €250 → credit €200.
        items = ((Decimal("1000.00"), Decimal("200.00"), Decimal("0.00")),)
        result = foreign_tax_credit_32d5_cap_2025(items, capital_tax_rate=Decimal("0.25"))
        self.assertEqual(result, Decimal("200.00"))

    def test_ftc_cap_above_item_cap(self) -> None:
        # Foreign tax €300 on €1,000 income at 25% → cap €250 → credit €250.
        items = ((Decimal("1000.00"), Decimal("300.00"), Decimal("0.00")),)
        result = foreign_tax_credit_32d5_cap_2025(items, capital_tax_rate=Decimal("0.25"))
        self.assertEqual(result, Decimal("250.00"))

    def test_treaty_nonzero_credit_fails_closed(self) -> None:
        # Manual treaty credits not supported — credit through § 32d(5) instead.
        with self.assertRaises(NotImplementedError):
            treaty_relieved_capital_tax_2025(
                Decimal("1000.00"), Decimal("55.00"), Decimal("10.00")
            )


if __name__ == "__main__":
    unittest.main()
