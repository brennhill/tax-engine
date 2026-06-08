"""§ 33b EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 33b EStG (https://www.gesetze-im-internet.de/estg/__33b.html).
Amendment: Behinderten-Pauschbetragsgesetz, BGBl. I 2020 S. 2770.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from law.germany.year_2025.estg.p33b import (
    BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR,
    BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR,
    behinderung_pauschbetrag_2025,
    child_disability_pauschbetrag_for_transferral_2025,
    disability_pauschbetrag_2025,
)
from tax_pipeline.y2025.germany_law import (
    BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR as PROD_TABLE,
    BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR as PROD_HB,
    behinderung_pauschbetrag_2025 as prod_behinderung,
    child_disability_pauschbetrag_for_transferral_2025 as prod_child_transferral,
    disability_pauschbetrag_2025 as prod_disability,
)


class P33bEstgIdentityTest(unittest.TestCase):
    def test_table_matches_production(self) -> None:
        self.assertEqual(BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR, PROD_TABLE)

    def test_hilflos_blind_matches_production(self) -> None:
        self.assertEqual(BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR, PROD_HB)

    def test_disability_pauschbetrag_matches_production(self) -> None:
        for grade in (0, 19, 20, 35, 50, 87, 100):
            self.assertEqual(
                disability_pauschbetrag_2025(grade), prod_disability(grade)
            )

    def test_disability_pauschbetrag_helpless_matches_production(self) -> None:
        self.assertEqual(
            disability_pauschbetrag_2025(50, helpless_or_blind=True),
            prod_disability(50, helpless_or_blind=True),
        )

    def test_behinderung_pauschbetrag_matches_production(self) -> None:
        for grade in (0, 20, 50, 100):
            self.assertEqual(
                behinderung_pauschbetrag_2025(gdb=grade, hilflos_or_blind=False),
                prod_behinderung(gdb=grade, hilflos_or_blind=False),
            )

    def test_child_transferral_matches_production(self) -> None:
        child = SimpleNamespace(disability_gdb=50, disability_helpless_or_blind=False)
        self.assertEqual(
            child_disability_pauschbetrag_for_transferral_2025(
                child=child, transfer_election_active=True
            ),
            prod_child_transferral(child=child, transfer_election_active=True),
        )


class P33bEstgStatuteTest(unittest.TestCase):
    def test_gdb_50_is_1140(self) -> None:
        # § 33b Abs. 3 Satz 2 EStG (post-2021 doubling, BGBl. I 2020 S. 2770).
        self.assertEqual(BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[50], Decimal("1140.00"))

    def test_gdb_100_is_2840(self) -> None:
        self.assertEqual(BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[100], Decimal("2840.00"))

    def test_hilflos_or_blind_is_7400(self) -> None:
        # § 33b Abs. 3 Satz 3 EStG.
        self.assertEqual(BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR, Decimal("7400.00"))

    def test_grade_below_20_has_no_pauschbetrag(self) -> None:
        # § 33b Abs. 3 Satz 2 EStG: no allowance below GdB 20.
        self.assertEqual(disability_pauschbetrag_2025(15), Decimal("0.00"))

    def test_non_decadic_grade_rounds_down(self) -> None:
        # GdB 35 → GdB 30 row (€620).
        self.assertEqual(disability_pauschbetrag_2025(35), Decimal("620.00"))
        # GdB 87 → GdB 80 row (€2,120).
        self.assertEqual(disability_pauschbetrag_2025(87), Decimal("2120.00"))

    def test_helpless_supersedes_grade(self) -> None:
        # § 33b Abs. 3 Satz 3 EStG: hilflos overrides the schedule.
        self.assertEqual(
            disability_pauschbetrag_2025(50, helpless_or_blind=True),
            Decimal("7400.00"),
        )

    def test_behinderung_pauschbetrag_strict_decadic(self) -> None:
        # Stricter than disability_pauschbetrag_2025: rejects non-decadic.
        with self.assertRaises(ValueError):
            behinderung_pauschbetrag_2025(gdb=35, hilflos_or_blind=False)


if __name__ == "__main__":
    unittest.main()
