"""§ 33 Abs. 3 EStG zumutbare Belastung at AGI bracket transitions.

Authority: § 33 Abs. 3 EStG (slab progression schedule); BFH VI R 75/14
(19.01.2017) confirms slab (not replacement) progression.

URL: https://www.gesetze-im-internet.de/estg/__33.html

Bracket boundaries: € 15,340.00 and € 51,130.00 (Gesamtbetrag der
Einkünfte). Rates depend on family category::

    single_no_children       → 5 % / 6 % / 7 %
    joint_or_few_children    → 4 % / 5 % / 6 %
    many_children            → 1 % / 1 % / 2 %

This test pins the slab-progression at the exact bracket transitions:
the value at € 15,340 is the band-A·rate-A only; the value at
€ 15,340.01 adds €0.01·rate-B; both round to identical cents at this
boundary because rate-B·€0.01 < €0.01.

It also pins the value just above € 51,130 to confirm rate-C kicks in
correctly.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p33 import (
    ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR,
    zumutbare_belastung_2025,
)


class P33ZumutbareBracketBoundaryTest(unittest.TestCase):
    """§ 33 Abs. 3 EStG slab progression at € 15,340 / € 51,130."""

    def test_brackets_match_statute(self) -> None:
        bracket_a, bracket_b = ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR
        self.assertEqual(bracket_a, Decimal("15340.00"))
        self.assertEqual(bracket_b, Decimal("51130.00"))

    def test_slab_progression_at_bracket_transitions(self) -> None:
        # § 33 Abs. 3 EStG slab progression. Each row pins one boundary or
        # boundary-adjacent value across the three family categories so a
        # rate-table change OR a slab→replacement regression is caught at
        # the bracket-transition cents.
        cases = (
            # single_no_children: 5 % / 6 % / 7 %
            (Decimal("15340.00"), "single_no_children", Decimal("767.00"),
             "first bracket boundary: 15340*0.05"),
            # +0.01 in band B; 0.0006 quantizes to 0.00 → still €767.00.
            (Decimal("15340.01"), "single_no_children", Decimal("767.00"),
             "+0.01 in band B; 0.0006 quantizes to band-A total"),
            (Decimal("51130.00"), "single_no_children", Decimal("2914.40"),
             "second bracket boundary: 767 + 35790*0.06"),
            (Decimal("51130.01"), "single_no_children", Decimal("2914.40"),
             "+0.01 in band C; 0.0007 quantizes to second-bracket total"),
            (Decimal("60000.00"), "single_no_children", Decimal("3535.30"),
             "well into band C: 767 + 2147.40 + 8870*0.07"),
            # joint_or_few_children: 4 % / 5 % / 6 %
            (Decimal("15340.00"), "joint_or_few_children", Decimal("613.60"),
             "first bracket boundary, joint: 15340*0.04"),
            (Decimal("51130.00"), "joint_or_few_children", Decimal("2403.10"),
             "second bracket boundary, joint: 613.60 + 35790*0.05"),
            # many_children: 1 % / 1 % / 2 %
            (Decimal("51130.00"), "many_children", Decimal("511.30"),
             "second bracket boundary, many_children: 153.40 + 357.90"),
            (Decimal("60000.00"), "many_children", Decimal("688.70"),
             "well into band C, many_children: 153.40 + 357.90 + 8870*0.02"),
        )
        for gde, category, expected, note in cases:
            with self.subTest(gde=gde, category=category, note=note):
                self.assertEqual(
                    zumutbare_belastung_2025(
                        gesamtbetrag_der_einkuenfte_eur=gde,
                        family_category=category,
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
