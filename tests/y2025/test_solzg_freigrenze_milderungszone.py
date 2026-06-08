"""§ 3 Abs. 3 / § 4 SolzG 1995 Freigrenze + Milderungszone boundaries.

Authority:
- § 3 Abs. 3 SolzG 1995 — Freigrenze (single €19,950 / joint €39,900)
- § 4 Satz 1 SolzG 1995 — 5,5 % Zuschlagssatz
- § 4 Satz 2 SolzG 1995 — Milderungszone (cap = 11,9 % × (festgesetzte
  ESt − Freigrenze)) so the surcharge phases in smoothly above the
  Freigrenze.

URL: https://www.gesetze-im-internet.de/solzg_1995/__3.html
URL: https://www.gesetze-im-internet.de/solzg_1995/__4.html

Pinned values:
- AT the exact Freigrenze (€19,950 single / €39,900 joint) → soli 0.
- ONE CENT past the Freigrenze → cap binds (Milderungszone).
- Inside the Milderungszone the 11,9 % cap binds.
- AT the upper end of the Milderungszone (around €37,094 for single
  posture) the cap exactly meets the 5,5 % full rate; above that the
  raw 5,5 % rate binds.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.solzg.p4 import (
    SOLI_JOINT_THRESHOLD_EUR,
    SOLI_MITIGATION_RATE,
    SOLI_SINGLE_THRESHOLD_EUR,
    german_soli_assessment_2025,
)


class SoliFreigrenzeBoundaryTest(unittest.TestCase):
    """§ 3 Abs. 3 SolzG 1995: AT and just past the Freigrenze."""

    def test_freigrenze_constants_match_2025(self) -> None:
        # § 3 Abs. 3 SolzG 1995, BGBl. I 2019 S. 2115.
        self.assertEqual(SOLI_SINGLE_THRESHOLD_EUR, Decimal("19950.00"))
        self.assertEqual(SOLI_JOINT_THRESHOLD_EUR, Decimal("39900.00"))
        self.assertEqual(SOLI_MITIGATION_RATE, Decimal("0.119"))

    def test_freigrenze_and_milderungszone_boundaries(self) -> None:
        # § 3 Abs. 3 SolzG 1995 Freigrenze + § 4 Satz 2 Milderungszone
        # cap. Each row pins one boundary; covers single + joint
        # postures and the upper bound where the cap stops binding.
        cases = (
            # Single Freigrenze + Milderungszone.
            (Decimal("19950.00"), "single", Decimal("0.00"),
             "at single Freigrenze: soli 0"),
            (Decimal("19950.01"), "single", Decimal("0.00"),
             "+0.01: cap = 0.00119 floors to 0"),
            (Decimal("20000.00"), "single", Decimal("5.95"),
             "inside Milderungszone: cap binds at 0.119·50"),
            # Single upper Milderungszone bound (cap → raw 5.5 % crossover).
            (Decimal("37094"), "single", Decimal("2040.13"),
             "just below upper bound: cap still binds (€0.04 short of raw)"),
            (Decimal("37096"), "single", Decimal("2040.28"),
             "at upper bound: cap = raw 5.5 % rate"),
            (Decimal("50000"), "single", Decimal("2750.00"),
             "above upper bound: raw 5.5 % binds"),
            # Joint Freigrenze + Milderungszone.
            (Decimal("39900.00"), "married_joint", Decimal("0.00"),
             "at joint Freigrenze: soli 0"),
            (Decimal("39900.01"), "married_joint", Decimal("0.00"),
             "+0.01 joint: cap = 0.00119 floors to 0"),
        )
        for est, posture, expected, note in cases:
            with self.subTest(est=est, posture=posture, note=note):
                self.assertEqual(
                    german_soli_assessment_2025(est, filing_posture=posture),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
