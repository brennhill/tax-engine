"""§ 32 EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 32 EStG (https://www.gesetze-im-internet.de/estg/__32.html).
Asserts the same numeric outcomes as the production rule via the
shadow copy in law/germany/year_2025/estg/p32.py.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p32 import (
    BEA_FREIBETRAG_2025_EUR,
    BEA_FREIBETRAG_PER_PARENT_2025_EUR,
    COMBINED_KINDERFREIBETRAG_2025_EUR,
    KINDERFREIBETRAG_2025_EUR,
    KINDERFREIBETRAG_PER_PARENT_2025_EUR,
    aggregate_germany_children_facts_2025,
    kinderfreibetrag_for_child_2025,
    kinderfreibetrag_per_child_2025_eur,
)
from tax_pipeline.y2025.germany_law import (
    BEA_FREIBETRAG_2025_EUR as PROD_BEA,
    COMBINED_KINDERFREIBETRAG_2025_EUR as PROD_COMBINED,
    KINDERFREIBETRAG_2025_EUR as PROD_KFB,
    aggregate_germany_children_facts_2025 as prod_aggregate,
    kinderfreibetrag_for_child_2025 as prod_kfb_child,
)


class P32EstgIdentityTest(unittest.TestCase):
    def test_kinderfreibetrag_combined_matches_production(self) -> None:
        self.assertEqual(KINDERFREIBETRAG_2025_EUR, PROD_KFB)

    def test_bea_combined_matches_production(self) -> None:
        self.assertEqual(BEA_FREIBETRAG_2025_EUR, PROD_BEA)

    def test_combined_total_matches_production(self) -> None:
        self.assertEqual(COMBINED_KINDERFREIBETRAG_2025_EUR, PROD_COMBINED)

    def test_per_child_function_matches_production(self) -> None:
        # Various postures + months.
        for posture in ("single", "married_joint", "married_separate"):
            for months in (0, 6, 12):
                self.assertEqual(
                    kinderfreibetrag_for_child_2025(months, filing_posture=posture),
                    prod_kfb_child(months, filing_posture=posture),
                )

    def test_aggregator_matches_production(self) -> None:
        # Use the production Child2025 dataclass so the aggregator can
        # consume identical input on both sides.
        from tax_pipeline.y2025.germany_law import Child2025

        child = Child2025(
            child_id="c1",
            name="Lina",
            date_of_birth="2018-04-01",
            ssn="",
            itin="",
            steuer_id="",
            relationship="qualifying_child",
            months_in_household=12,
            months_in_us_household=0,
            annual_gross_income_eur=Decimal("0.00"),
            annual_gross_income_usd=Decimal("0.00"),
            kindergeld_received_eur=Decimal("3000.00"),
            kindergeld_recipient="taxpayer",
            disability_gdb=0,
            disability_helpless_or_blind=False,
        )
        s = aggregate_germany_children_facts_2025(
            (child,), filing_posture="married_joint"
        )
        p = prod_aggregate(
            (child,), filing_posture="married_joint"
        )
        self.assertEqual(s.children_count, p.children_count)
        self.assertEqual(s.kinderfreibetrag_total_eur, p.kinderfreibetrag_total_eur)
        self.assertEqual(s.kindergeld_received_total_eur, p.kindergeld_received_total_eur)


class P32EstgStatuteTest(unittest.TestCase):
    def test_kinderfreibetrag_per_parent_2025(self) -> None:
        # § 32 Abs. 6 Satz 1 EStG (Steuerfortentwicklungsgesetz 2024).
        self.assertEqual(KINDERFREIBETRAG_PER_PARENT_2025_EUR, Decimal("3336"))

    def test_bea_freibetrag_per_parent_2025(self) -> None:
        # § 32 Abs. 6 Satz 1 EStG (BEA-Freibetrag).
        self.assertEqual(BEA_FREIBETRAG_PER_PARENT_2025_EUR, Decimal("1464"))

    def test_combined_per_child_is_9600(self) -> None:
        self.assertEqual(COMBINED_KINDERFREIBETRAG_2025_EUR, Decimal("9600"))

    def test_per_child_full_year_single_or_joint(self) -> None:
        result = kinderfreibetrag_for_child_2025(12, filing_posture="married_joint")
        self.assertEqual(result, Decimal("9600.00"))

    def test_per_child_full_year_married_separate(self) -> None:
        # § 32 Abs. 6 Satz 1/2 EStG halves to €4,800 per spouse.
        result = kinderfreibetrag_for_child_2025(12, filing_posture="married_separate")
        self.assertEqual(result, Decimal("4800.00"))

    def test_per_child_partial_year_six_months_joint(self) -> None:
        # 6/12 × €9,600 = €4,800.
        result = kinderfreibetrag_for_child_2025(6, filing_posture="married_joint")
        self.assertEqual(result, Decimal("4800.00"))

    def test_per_child_helper_returns_full_year_amount(self) -> None:
        self.assertEqual(
            kinderfreibetrag_per_child_2025_eur(filing_posture="married_joint"),
            Decimal("9600"),
        )
        self.assertEqual(
            kinderfreibetrag_per_child_2025_eur(filing_posture="married_separate"),
            Decimal("4800"),
        )

    def test_unsupported_posture_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            kinderfreibetrag_for_child_2025(12, filing_posture="head_of_household")


if __name__ == "__main__":
    unittest.main()
