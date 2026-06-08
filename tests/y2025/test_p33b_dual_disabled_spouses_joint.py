"""§ 33b Abs. 5 EStG: dual-disabled spouses joint assessment.

Authority: § 33b Abs. 3 EStG (per-person Pauschbetrag schedule),
§ 33b Abs. 5 EStG (per-child transferral, 50/50 default split between
parents), § 26b EStG (Zusammenveranlagung — joint summing of incomes
and Pauschbeträge).
URL: https://www.gesetze-im-internet.de/estg/__33b.html
URL: https://www.gesetze-im-internet.de/estg/__26b.html

The existing pauschbetrag tests cover (a) a single disabled spouse
with optional child transferral and (b) a non-disabled couple with
child transferral. They DON'T pin the case of two spouses BOTH having
their own GdB — § 26b EStG joint assessment must sum each spouse's
Pauschbetrag (per § 33b Abs. 3 EStG schedule) into the household
total without any silent halving or capping.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from tax_pipeline.y2025.germany_ordinary_rules import (
    de25_behinderung_pauschbetrag,
)


def _person(gdb: int, hilflos: bool = False) -> SimpleNamespace:
    return SimpleNamespace(gdb=gdb, hilflos_or_blind=hilflos)


class DualDisabledSpousesJointAssessmentTest(unittest.TestCase):
    """§ 26b EStG sums each spouse's § 33b Abs. 3 EStG Pauschbetrag.

    The expected per-spouse amounts come from the statutory schedule:
    GdB 50 → €1,140; GdB 80 → €2,120; GdB 100 → €2,840;
    hilflos/blind → €7,400 (§ 33b Abs. 3 Satz 3 EStG).
    """

    def test_both_spouses_gdb_50_sums_to_2280(self) -> None:
        # Each spouse independently qualifies at GdB 50 → €1,140.
        # § 26b EStG joint assessment: 1140 + 1140 = €2,280.
        facts = {
            "de.ordinary.people": (
                _person(gdb=50),
                _person(gdb=50),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("0.00"),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("2280.00"))
        self.assertEqual(out["parents_only_total_eur"], Decimal("2280.00"))
        # Each spouse contributes their own Pauschbetrag — no
        # halving / averaging: 1140 + 1140.
        self.assertEqual(out["by_person"][0], Decimal("1140.00"))
        self.assertEqual(out["by_person"][1], Decimal("1140.00"))

    def test_asymmetric_gdb_50_and_gdb_80_sums_to_3260(self) -> None:
        # § 26b EStG: each spouse keeps their statutory amount.
        # 1140 (GdB 50) + 2120 (GdB 80) = €3,260.
        facts = {
            "de.ordinary.people": (
                _person(gdb=50),
                _person(gdb=80),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("0.00"),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("3260.00"))
        self.assertEqual(out["by_person"][0], Decimal("1140.00"))
        self.assertEqual(out["by_person"][1], Decimal("2120.00"))

    def test_one_spouse_hilflos_other_gdb_100_sums_to_10240(self) -> None:
        # § 33b Abs. 3 Satz 3 EStG: hilflose → €7,400 (supersedes the
        # GdB schedule for that spouse). Other spouse at GdB 100 → €2,840.
        # Joint assessment: 7400 + 2840 = €10,240.
        facts = {
            "de.ordinary.people": (
                _person(gdb=100, hilflos=True),
                _person(gdb=100),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("0.00"),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("10240.00"))
        self.assertEqual(out["by_person"][0], Decimal("7400.00"))
        self.assertEqual(out["by_person"][1], Decimal("2840.00"))

    def test_both_spouses_disabled_plus_child_transfer_50_50_split(self) -> None:
        # Both spouses GdB 80 (€2,120 each) plus a €1,440 child
        # transferral split 50/50 per § 33b Abs. 5 Satz 3 EStG default.
        # Per-spouse: 2120 + 720 = €2,840. Household: 2 · 2840 = €5,680.
        facts = {
            "de.ordinary.people": (
                _person(gdb=80),
                _person(gdb=80),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("1440.00"),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("5680.00"))
        self.assertEqual(out["parents_only_total_eur"], Decimal("4240.00"))
        self.assertEqual(out["child_transferred_eur"], Decimal("1440.00"))
        # 50/50 split: each spouse gets €720 of the child transferral
        # plus their own €2,120 Pauschbetrag.
        self.assertEqual(out["by_person"][0], Decimal("2840.00"))
        self.assertEqual(out["by_person"][1], Decimal("2840.00"))

    def test_household_total_invariant_holds_for_dual_disabled(self) -> None:
        # Sum-of-per-person == household total invariant. Picked an
        # asymmetric pair so the invariant is exercised on a non-trivial
        # allocation.
        facts = {
            "de.ordinary.people": (
                _person(gdb=70),
                _person(gdb=30),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("620.00"),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        # GdB 70 → €1,780; GdB 30 → €620; child transferral €620.
        # Total: 1780 + 620 + 620 = €3,020.
        self.assertEqual(out["total_eur"], Decimal("3020.00"))
        self.assertEqual(
            sum(out["by_person"], Decimal("0.00")),
            out["total_eur"],
        )


if __name__ == "__main__":
    unittest.main()
