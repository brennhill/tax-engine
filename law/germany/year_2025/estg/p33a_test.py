"""§ 33a EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 33a EStG (https://www.gesetze-im-internet.de/estg/__33a.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p33a import (
    UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR,
    UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS,
    unterhaltsleistungen_deductible_2025,
)
from tax_pipeline.y2025.germany_law import (
    UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR as PROD_FB,
    UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS as PROD_RELS,
    unterhaltsleistungen_deductible_2025 as prod_fn,
)


class P33aEstgIdentityTest(unittest.TestCase):
    def test_freibetrag_matches_production(self) -> None:
        self.assertEqual(
            UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR, PROD_FB
        )

    def test_relationships_match_production(self) -> None:
        self.assertEqual(UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS, PROD_RELS)

    def test_function_matches_production_no_eigenbezug(self) -> None:
        s = unterhaltsleistungen_deductible_2025(
            support_payments_eur=Decimal("10000.00"),
            recipient_income_eur=Decimal("0.00"),
            relationship="parent",
            grundfreibetrag_eur=Decimal("12096.00"),
        )
        p = prod_fn(
            support_payments_eur=Decimal("10000.00"),
            recipient_income_eur=Decimal("0.00"),
            relationship="parent",
            grundfreibetrag_eur=Decimal("12096.00"),
        )
        self.assertEqual(s, p)

    def test_function_matches_production_with_eigenbezug(self) -> None:
        s = unterhaltsleistungen_deductible_2025(
            support_payments_eur=Decimal("10000.00"),
            recipient_income_eur=Decimal("2000.00"),
            relationship="parent",
            grundfreibetrag_eur=Decimal("12096.00"),
        )
        p = prod_fn(
            support_payments_eur=Decimal("10000.00"),
            recipient_income_eur=Decimal("2000.00"),
            relationship="parent",
            grundfreibetrag_eur=Decimal("12096.00"),
        )
        self.assertEqual(s, p)


class P33aEstgStatuteTest(unittest.TestCase):
    def test_eigenbezug_freibetrag_is_624(self) -> None:
        # § 33a Abs. 1 Satz 5 EStG.
        self.assertEqual(
            UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR,
            Decimal("624.00"),
        )

    def test_eigenbezug_below_freibetrag_does_not_reduce_cap(self) -> None:
        # €600 < €624 → no reduction.
        result = unterhaltsleistungen_deductible_2025(
            support_payments_eur=Decimal("12000.00"),
            recipient_income_eur=Decimal("600.00"),
            relationship="parent",
            grundfreibetrag_eur=Decimal("12096.00"),
        )
        # Full deduction up to €12,000.
        self.assertEqual(result, Decimal("12000.00"))

    def test_unsupported_relationship_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("100.00"),
                recipient_income_eur=Decimal("0.00"),
                relationship="cousin",
                grundfreibetrag_eur=Decimal("12096.00"),
            )


if __name__ == "__main__":
    unittest.main()
