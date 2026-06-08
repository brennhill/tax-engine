"""§ 4 SolzG 1995 numeric tests, anchored to gesetze-im-internet.de.

Authority: § 3 Abs. 3 SolzG 1995 (Freigrenze) + § 4 SolzG 1995 (5,5 %
rate, 11,9 % Milderungszone).
- https://www.gesetze-im-internet.de/solzg_1995/__3.html
- https://www.gesetze-im-internet.de/solzg_1995/__4.html
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
from tax_pipeline.y2025.germany_law import (
    SOLI_JOINT_THRESHOLD_EUR as PROD_JOINT,
    SOLI_MITIGATION_RATE as PROD_MIT,
    SOLI_SINGLE_THRESHOLD_EUR as PROD_SINGLE,
    german_soli_assessment_2025 as prod_fn,
)


class P4SolzgIdentityTest(unittest.TestCase):
    def test_single_threshold_matches_production(self) -> None:
        self.assertEqual(SOLI_SINGLE_THRESHOLD_EUR, PROD_SINGLE)

    def test_joint_threshold_matches_production(self) -> None:
        self.assertEqual(SOLI_JOINT_THRESHOLD_EUR, PROD_JOINT)

    def test_mitigation_rate_matches_production(self) -> None:
        self.assertEqual(SOLI_MITIGATION_RATE, PROD_MIT)

    def test_assessment_matches_production_at_zero(self) -> None:
        s = german_soli_assessment_2025(Decimal("0.00"), filing_posture="married_joint")
        p = prod_fn(Decimal("0.00"), filing_posture="married_joint")
        self.assertEqual(s, p)

    def test_assessment_below_joint_freigrenze(self) -> None:
        s = german_soli_assessment_2025(Decimal("30000.00"), filing_posture="married_joint")
        p = prod_fn(Decimal("30000.00"), filing_posture="married_joint")
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("0.00"))

    def test_assessment_in_milderungszone_joint(self) -> None:
        # Just over the joint Freigrenze of €39.900 — Milderungszone caps the surcharge.
        s = german_soli_assessment_2025(Decimal("40000.00"), filing_posture="married_joint")
        p = prod_fn(Decimal("40000.00"), filing_posture="married_joint")
        self.assertEqual(s, p)

    def test_assessment_above_milderungszone_joint(self) -> None:
        # High enough that full 5,5 % rate applies.
        s = german_soli_assessment_2025(Decimal("100000.00"), filing_posture="married_joint")
        p = prod_fn(Decimal("100000.00"), filing_posture="married_joint")
        self.assertEqual(s, p)

    def test_assessment_single_posture(self) -> None:
        s = german_soli_assessment_2025(Decimal("25000.00"), filing_posture="single")
        p = prod_fn(Decimal("25000.00"), filing_posture="single")
        self.assertEqual(s, p)

    def test_assessment_married_separate_posture(self) -> None:
        s = german_soli_assessment_2025(Decimal("25000.00"), filing_posture="married_separate")
        p = prod_fn(Decimal("25000.00"), filing_posture="married_separate")
        self.assertEqual(s, p)


class P4SolzgStatuteTest(unittest.TestCase):
    def test_single_threshold_is_19950_eur(self) -> None:
        # § 3 Abs. 3 SolzG 1995 (single posture).
        self.assertEqual(SOLI_SINGLE_THRESHOLD_EUR, Decimal("19950.00"))

    def test_joint_threshold_is_39900_eur(self) -> None:
        # § 3 Abs. 3 SolzG 1995 (joint posture, twice the single).
        self.assertEqual(SOLI_JOINT_THRESHOLD_EUR, Decimal("39900.00"))

    def test_mitigation_rate_is_11_9_percent(self) -> None:
        # § 4 Satz 2 SolzG 1995 Milderungszone rate.
        self.assertEqual(SOLI_MITIGATION_RATE, Decimal("0.119"))

    def test_below_freigrenze_yields_zero(self) -> None:
        # § 3 Abs. 3 SolzG 1995: tax base ≤ Freigrenze → no Soli.
        self.assertEqual(
            german_soli_assessment_2025(SOLI_JOINT_THRESHOLD_EUR, filing_posture="married_joint"),
            Decimal("0.00"),
        )

    def test_unsupported_posture_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            german_soli_assessment_2025(Decimal("50000.00"), filing_posture="alien")


if __name__ == "__main__":
    unittest.main()
