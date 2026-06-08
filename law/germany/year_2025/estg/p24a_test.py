"""§ 24a EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 24a EStG (https://www.gesetze-im-internet.de/estg/__24a.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p24a import (
    ALTERSENTLASTUNGSBETRAG_2025_TABLE,
    ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS,
    altersentlastungsbetrag_2025,
)
from tax_pipeline.y2025.germany_law import (
    ALTERSENTLASTUNGSBETRAG_2025_TABLE as PROD_TABLE,
    ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS as PROD_AGE,
    altersentlastungsbetrag_2025 as prod_fn,
)


class P24aEstgIdentityTest(unittest.TestCase):
    def test_table_matches_production(self) -> None:
        self.assertEqual(ALTERSENTLASTUNGSBETRAG_2025_TABLE, PROD_TABLE)

    def test_age_threshold_matches_production(self) -> None:
        self.assertEqual(ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS, PROD_AGE)

    def test_function_matches_production_for_2024_cohort(self) -> None:
        # 2024 cohort: 13.6 %, cap €646.
        s = altersentlastungsbetrag_2025(
            birth_year=1960, eligible_income_eur=Decimal("3000.00")
        )
        p = prod_fn(birth_year=1960, eligible_income_eur=Decimal("3000.00"))
        self.assertEqual(s, p)

    def test_function_matches_production_for_pre_64_taxpayer(self) -> None:
        # Born 1962: turned 64 in 2026 → no allowance for 2025.
        s = altersentlastungsbetrag_2025(
            birth_year=1962, eligible_income_eur=Decimal("3000.00")
        )
        p = prod_fn(birth_year=1962, eligible_income_eur=Decimal("3000.00"))
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("0.00"))


class P24aEstgStatuteTest(unittest.TestCase):
    def test_2023_cohort_uses_post_wachstumschancengesetz_value(self) -> None:
        # F-C6: Wachstumschancengesetz halved the per-cohort rate-step from 2023.
        # 2023 row must be 14.0% / €665, NOT a re-use of the 2022 €684 cap.
        rate, cap = ALTERSENTLASTUNGSBETRAG_2025_TABLE[2023]
        self.assertEqual(rate, Decimal("0.140"))
        self.assertEqual(cap, Decimal("665"))

    def test_2025_cohort_value(self) -> None:
        rate, cap = ALTERSENTLASTUNGSBETRAG_2025_TABLE[2025]
        self.assertEqual(rate, Decimal("0.132"))
        self.assertEqual(cap, Decimal("627"))

    def test_age_threshold_is_64(self) -> None:
        # § 24a Satz 3 EStG (Vollendung des 64. Lebensjahres).
        self.assertEqual(ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS, 64)

    def test_taxpayer_who_turns_64_in_assessment_year_does_not_qualify(self) -> None:
        # § 24a Satz 3 EStG: applies starting the year AFTER turning 64.
        # Born 1961 → turns 64 in 2025 → no 2025 allowance.
        result = altersentlastungsbetrag_2025(
            birth_year=1961, eligible_income_eur=Decimal("10000.00")
        )
        self.assertEqual(result, Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
