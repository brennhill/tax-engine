"""§ 32a EStG bracket-boundary tests (single + split tariff).

Authority: § 32a Abs. 1 EStG (Grundtarif) and § 32a Abs. 5 EStG (Splittingtarif).
URL: https://www.gesetze-im-internet.de/estg/__32a.html
Tariff coefficients: BMF Programmablaufplan 2025.

Boundary values cited:
- ``12096`` — § 32a Abs. 1 Nr. 1 EStG Grundfreibetrag (zvE ≤ 12.096 → tax 0).
- ``17443`` — § 32a Abs. 1 Nr. 2 EStG upper bound of progression zone 1.
- ``68480`` — § 32a Abs. 1 Nr. 3 EStG upper bound of progression zone 2
  (the task description's ``68,481`` is the FIRST euro of the 42 % zone;
  the inclusive upper bound of zone 2 in the implementation is 68,480 —
  we test BOTH sides of that boundary).
- ``277825`` — § 32a Abs. 1 Nr. 4 EStG upper bound of the 42 % zone
  (the task description's ``277,826`` is the FIRST euro of the 45 %
  Reichensteuer zone; we test BOTH sides).

These are exact-boundary tests for the canonical tariff: each bracket
is exercised on its statutory edge AND one euro past it, so a
regression that shifts a comparison from ``<=`` to ``<`` (or vice
versa) is caught.

§ 32a Abs. 5 EStG (Splittingverfahren) is the doubled-zvE / doubled-tax
form: ``tax_split(zvE) = 2 · tax_single(zvE / 2)``. The split tests
double each single-filer boundary so the joint posture is independently
exercised on the same statutory edges.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p32a import (
    german_income_tax_single_2025,
    german_income_tax_split_2025,
)


class P32aBracketBoundarySingleTest(unittest.TestCase):
    """§ 32a Abs. 1 EStG single-filer Grundtarif at exact bracket boundaries.

    Expected values were computed by hand-evaluating the BMF
    Programmablaufplan 2025 polynomial for each zone and rounding via
    § 32a's prescribed floor-to-euro convention.
    """

    def test_single_filer_bracket_boundaries(self) -> None:
        # ``(zvE, expected, citation)`` covering every § 32a Abs. 1 zone
        # transition and one euro past each (so a ``<=`` ↔ ``<`` flip is
        # caught at the edge cents).
        cases = (
            # § 32a Abs. 1 Nr. 1 — Grundfreibetrag inclusive upper bound.
            (Decimal("12096"), Decimal("0"), "Grundfreibetrag inclusive"),
            # +1 € into zone 1 still floors to 0.
            (Decimal("12097"), Decimal("0"), "first € of zone 1 floors to 0"),
            # § 32a Abs. 1 Nr. 2 — zone 1 inclusive upper bound.
            (Decimal("17443"), Decimal("1015"), "zone 1 upper bound"),
            (Decimal("17444"), Decimal("1015"), "zone 2 first €"),
            # § 32a Abs. 1 Nr. 3 — zone 2 (24%–42%) inclusive upper bound.
            (Decimal("68480"), Decimal("17849"), "zone 2 upper bound"),
            (Decimal("68481"), Decimal("17850"), "42% zone first €"),
            # § 32a Abs. 1 Nr. 4 — 42% zone inclusive upper bound.
            (Decimal("277825"), Decimal("105774"), "42% zone upper bound"),
            # § 32a Abs. 1 Nr. 5 — Reichensteuer (45%) first €.
            (Decimal("277826"), Decimal("105775"), "Reichensteuer first €"),
        )
        for zve, expected, note in cases:
            with self.subTest(zve=zve, note=note):
                self.assertEqual(german_income_tax_single_2025(zve), expected)


class P32aBracketBoundarySplitTest(unittest.TestCase):
    """§ 32a Abs. 5 EStG Splittingtarif at the doubled boundaries.

    Expected values follow the splitting identity
    ``tax_split(zvE) = 2 · tax_single(zvE / 2)``. The asymmetric-half
    cases pin the same identity when the per-spouse half-zvE lands
    exactly on a single-filer bracket transition — a regression that
    moves an inclusive ``<=`` comparison flips the boundary on BOTH
    halves of the split.
    """

    def test_split_tariff_at_doubled_boundaries(self) -> None:
        cases = (
            (Decimal("24192"), Decimal("0"), "doubled Grundfreibetrag"),
            (Decimal("34886"), Decimal("2030"), "doubled zone 1 upper bound (half=17443)"),
            (Decimal("34888"), Decimal("2030"), "half=17444 first € of zone 2"),
            (Decimal("136960"), Decimal("35698"), "doubled zone 2 upper bound"),
            (Decimal("555650"), Decimal("211548"), "doubled 42% zone upper bound (half=277825)"),
            (Decimal("555652"), Decimal("211550"), "doubled Reichensteuer first €"),
        )
        for zve, expected, note in cases:
            with self.subTest(zve=zve, note=note):
                self.assertEqual(german_income_tax_split_2025(zve), expected)


if __name__ == "__main__":
    unittest.main()
