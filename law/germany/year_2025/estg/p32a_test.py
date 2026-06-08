"""§ 32a EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 32a EStG (https://www.gesetze-im-internet.de/estg/__32a.html).
Tariff coefficients sourced from the official 2025 BMF
Programmablaufplan.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p32a import (
    TARIFF_2025_GROUND_ALLOWANCE_EUR,
    TARIFF_2025_PROGRESS_ZONE_1_END_EUR,
    TARIFF_2025_PROGRESS_ZONE_2_END_EUR,
    TARIFF_2025_TOP_RATE_START_EUR,
    german_income_tax_single_2025,
    german_income_tax_split_2025,
)
from tax_pipeline.y2025.germany_law import (
    TARIFF_2025_GROUND_ALLOWANCE_EUR as PROD_GA,
    TARIFF_2025_PROGRESS_ZONE_1_END_EUR as PROD_Z1,
    TARIFF_2025_PROGRESS_ZONE_2_END_EUR as PROD_Z2,
    TARIFF_2025_TOP_RATE_START_EUR as PROD_TOP,
    german_income_tax_single_2025 as prod_single,
    german_income_tax_split_2025 as prod_split,
)


class P32aEstgIdentityTest(unittest.TestCase):
    def test_ground_allowance_matches_production(self) -> None:
        self.assertEqual(TARIFF_2025_GROUND_ALLOWANCE_EUR, PROD_GA)

    def test_zone_1_end_matches_production(self) -> None:
        self.assertEqual(TARIFF_2025_PROGRESS_ZONE_1_END_EUR, PROD_Z1)

    def test_zone_2_end_matches_production(self) -> None:
        self.assertEqual(TARIFF_2025_PROGRESS_ZONE_2_END_EUR, PROD_Z2)

    def test_top_rate_start_matches_production(self) -> None:
        self.assertEqual(TARIFF_2025_TOP_RATE_START_EUR, PROD_TOP)

    def test_single_tax_matches_production_for_each_zone(self) -> None:
        for zve in (
            Decimal("0"),
            Decimal("12096"),  # at Grundfreibetrag
            Decimal("15000"),  # progression zone 1
            Decimal("30000"),  # progression zone 2
            Decimal("100000"),  # 42% zone
            Decimal("300000"),  # 45% zone
        ):
            self.assertEqual(
                german_income_tax_single_2025(zve), prod_single(zve), msg=f"zve={zve}"
            )

    def test_split_tax_matches_production(self) -> None:
        for zve in (
            Decimal("24192"),
            Decimal("60000"),
            Decimal("200000"),
        ):
            self.assertEqual(german_income_tax_split_2025(zve), prod_split(zve))


class P32aEstgStatuteTest(unittest.TestCase):
    def test_grundfreibetrag_2025_is_12096(self) -> None:
        # Steuerfortentwicklungsgesetz 2024.
        self.assertEqual(TARIFF_2025_GROUND_ALLOWANCE_EUR, Decimal("12096"))

    def test_zero_zve_yields_zero_tax(self) -> None:
        self.assertEqual(german_income_tax_single_2025(Decimal("0")), Decimal("0"))

    def test_at_grundfreibetrag_yields_zero(self) -> None:
        # § 32a Abs. 1 Nr. 1 EStG: ZvE ≤ Grundfreibetrag → tax 0.
        self.assertEqual(
            german_income_tax_single_2025(TARIFF_2025_GROUND_ALLOWANCE_EUR),
            Decimal("0"),
        )

    def test_split_doubles_single_at_half_zve(self) -> None:
        # § 32a Abs. 5 EStG Splittingverfahren.
        zve = Decimal("60000")
        single_at_half = german_income_tax_single_2025(zve / Decimal("2"))
        self.assertEqual(german_income_tax_split_2025(zve), single_at_half * Decimal("2"))


if __name__ == "__main__":
    unittest.main()
