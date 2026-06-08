"""§ 33 EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 33 EStG (https://www.gesetze-im-internet.de/estg/__33.html).
Case law: BFH VI R 75/14 (19.01.2017) — slab progression on the brackets.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p33 import (
    ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR,
    ZUMUTBARE_BELASTUNG_2025_RATES,
    aussergewoehnliche_belastungen_deductible_2025,
    zumutbare_belastung_2025,
)
from tax_pipeline.y2025.germany_law import (
    ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR as PROD_BRACKETS,
    ZUMUTBARE_BELASTUNG_2025_RATES as PROD_RATES,
    aussergewoehnliche_belastungen_deductible_2025 as prod_deductible,
    zumutbare_belastung_2025 as prod_burden,
)


class P33EstgIdentityTest(unittest.TestCase):
    def test_brackets_match_production(self) -> None:
        self.assertEqual(ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR, PROD_BRACKETS)

    def test_rates_match_production(self) -> None:
        self.assertEqual(ZUMUTBARE_BELASTUNG_2025_RATES, PROD_RATES)

    def test_burden_matches_production(self) -> None:
        for category in ZUMUTBARE_BELASTUNG_2025_RATES:
            for income in (
                Decimal("10000.00"),
                Decimal("20000.00"),
                Decimal("60000.00"),
            ):
                s = zumutbare_belastung_2025(
                    gesamtbetrag_der_einkuenfte_eur=income, family_category=category
                )
                p = prod_burden(
                    gesamtbetrag_der_einkuenfte_eur=income, family_category=category
                )
                self.assertEqual(s, p)

    def test_deductible_matches_production(self) -> None:
        s = aussergewoehnliche_belastungen_deductible_2025(
            medical_expenses_eur=Decimal("3000.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("50000.00"),
            family_category="joint_or_few_children",
        )
        p = prod_deductible(
            medical_expenses_eur=Decimal("3000.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("50000.00"),
            family_category="joint_or_few_children",
        )
        self.assertEqual(s, p)


class P33EstgStatuteTest(unittest.TestCase):
    def test_brackets_are_15340_and_51130(self) -> None:
        # § 33 Abs. 3 EStG.
        self.assertEqual(ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR, (Decimal("15340.00"), Decimal("51130.00")))

    def test_single_no_children_rates(self) -> None:
        # § 33 Abs. 3 Satz 1 EStG.
        self.assertEqual(ZUMUTBARE_BELASTUNG_2025_RATES["single_no_children"], (Decimal("0.05"), Decimal("0.06"), Decimal("0.07")))

    def test_slab_progression_at_first_bracket(self) -> None:
        # Income exactly at first bracket: only band_a applies.
        # 15340 × 0.05 = 767.00 (single_no_children).
        result = zumutbare_belastung_2025(
            gesamtbetrag_der_einkuenfte_eur=Decimal("15340.00"),
            family_category="single_no_children",
        )
        self.assertEqual(result, Decimal("767.00"))

    def test_invalid_family_category_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            zumutbare_belastung_2025(
                gesamtbetrag_der_einkuenfte_eur=Decimal("10000.00"),
                family_category="invalid",
            )


if __name__ == "__main__":
    unittest.main()
