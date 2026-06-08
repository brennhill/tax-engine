"""Tests for § 33b Abs. 5 EStG transferral of a child's Behinderten-
Pauschbetrag to the parents — Gap 2.

The DE25-CHILDREN-DISABILITY-PAUSCHBETRAG sibling stage in the children
sub-graph re-emits the Pipeline 1 derived total for audit; the
ordinary stage DE25-BEHINDERUNG-PAUSCHBETRAG adds the same total to the
parents' household Pauschbetrag so the transferral flows through DE25-07
zvE → DE25-08 tariff at the parents' marginal rate.

Authority:
- § 33b Abs. 3 Satz 2 EStG (Pauschbetrag schedule by Grad der Behinderung):
  https://www.gesetze-im-internet.de/estg/__33b.html
- § 33b Abs. 3 Satz 3 EStG (erhöhter Pauschbetrag €7,400 for hilflos /
  blind / Pflegegrad 4 oder 5):
  https://www.gesetze-im-internet.de/estg/__33b.html
- § 33b Abs. 5 EStG (transferral of a qualifying child's Pauschbetrag
  to the parents):
  https://www.gesetze-im-internet.de/estg/__33b.html
- BGBl. I 2020 S. 2770 (Behinderten-Pauschbetragsgesetz, 2021 doubling
  carried into 2025).

Each numeric test asserts a concrete EUR amount derived from the dated
2025 § 33b Abs. 3 EStG schedule.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from typing import Any

from tax_pipeline.core.stages import execute_rule_graph
from tax_pipeline.y2025.derivation.germany_derivations import (
    CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY,
    CHILDREN_INPUT_FILING_POSTURE_KEY,
    CHILDREN_INPUT_RAW_KEY,
    CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL,
    derive_de25_children,
)
from tax_pipeline.y2025.germany_law import (
    Child2025,
    aggregate_germany_children_facts_2025,
    child_disability_pauschbetrag_for_transferral_2025,
    disability_pauschbetrag_2025,
)
from tax_pipeline.y2025.germany_children_rules import (
    de25_children_disability_pauschbetrag,
    germany_children_law_rules_2025,
)
from tax_pipeline.y2025.germany_ordinary_rules import (
    de25_behinderung_pauschbetrag,
)


def _child(
    *,
    child_id: str = "child-1",
    months: int = 12,
    recipient: str = "taxpayer",
    relationship: str = "qualifying_child",
    gdb: int = 0,
    helpless_or_blind: bool = False,
) -> Child2025:
    """Construct a synthetic Child2025 covering Gap 2 columns.

    Authority: § 32 Abs. 6 EStG / BKGG / § 33b Abs. 3 EStG. Sets the
    GdB grade and ``disability_helpless_or_blind`` so the per-child
    transferral helper can apply the §-33b-Abs.-3-EStG schedule.
    """
    # Authority: § 6 BKGG (https://www.gesetze-im-internet.de/bkgg_1996/__6.html);
    # Steuerfortentwicklungsgesetz 2024 raised the monthly Kindergeld to €255
    # effective 01.01.2025. Stale €250 was caught by F-DELAW-1 (commit 608861d).
    kindergeld_received = (
        Decimal("255.00") * Decimal(months)
        if recipient in {"taxpayer", "spouse"}
        else Decimal("0.00")
    )
    return Child2025(
        child_id=child_id,
        name=child_id,
        date_of_birth="2018-01-01",
        ssn="",
        itin="",
        steuer_id="",
        relationship=relationship,
        months_in_household=months,
        months_in_us_household=0,
        annual_gross_income_eur=Decimal("0.00"),
        annual_gross_income_usd=Decimal("0.00"),
        kindergeld_received_eur=kindergeld_received,
        kindergeld_recipient=recipient,
        disability_gdb=gdb,
        disability_helpless_or_blind=helpless_or_blind,
    )


class DisabilityPauschbetragScheduleTest(unittest.TestCase):
    """§ 33b Abs. 3 Satz 2 EStG schedule — concrete EUR amounts."""

    def test_disability_pauschbetrag_schedule(self) -> None:
        """§ 33b Abs. 3 Satz 2 EStG schedule + Satz 3 erhöhter Pauschbetrag.

        Authority: § 33b Abs. 3 Satz 2 EStG schedule per
        Behinderten-Pauschbetragsgesetz (BGBl. I 2020 S. 2770);
        § 33b Abs. 3 Satz 3 EStG erhöhter Pauschbetrag (€7,400 for
        hilflos / blind / Pflegegrad 4-5, mutually exclusive with the
        GdB schedule).
        """
        # ``(gdb, helpless_or_blind, expected)`` covering:
        # - sub-threshold GdB (statutory zero)
        # - decadic schedule rows
        # - non-decadic round-down
        # - § 33b Abs. 3 Satz 3 hilflos/blind override (regardless of GdB)
        cases = (
            (0, False, Decimal("0.00")),
            (15, False, Decimal("0.00")),
            (20, False, Decimal("384.00")),
            (30, False, Decimal("620.00")),
            (35, False, Decimal("620.00")),  # non-decadic rounds to 30
            (50, False, Decimal("1140.00")),
            (87, False, Decimal("2120.00")),  # non-decadic rounds to 80
            (100, False, Decimal("2840.00")),
            (0, True, Decimal("7400.00")),    # hilflos overrides at GdB 0
            (100, True, Decimal("7400.00")),  # hilflos overrides at GdB 100
        )
        for gdb, helpless, expected in cases:
            with self.subTest(gdb=gdb, helpless_or_blind=helpless):
                self.assertEqual(
                    disability_pauschbetrag_2025(gdb, helpless_or_blind=helpless),
                    expected,
                )

    def test_invalid_grade_fails_closed(self) -> None:
        """GdB outside [0, 100] raises ValueError per § 33b Abs. 3 EStG."""
        for grade in (-5, 110):
            with self.subTest(grade=grade):
                with self.assertRaises(ValueError):
                    disability_pauschbetrag_2025(grade)


class PerChildTransferralHelperTest(unittest.TestCase):
    """``child_disability_pauschbetrag_for_transferral_2025`` gate logic."""

    def test_returns_zero_when_election_inactive(self) -> None:
        """Election=False → forfeit per § 33b Abs. 5 Satz 1 EStG."""
        child = _child(gdb=80)
        amount = child_disability_pauschbetrag_for_transferral_2025(
            child=child,
            transfer_election_active=False,
        )
        self.assertEqual(amount, Decimal("0.00"))

    def test_returns_schedule_amount_when_election_active(self) -> None:
        """Election=True → per-child §-33b-Abs.-3 amount transferred.

        Authority: § 33b Abs. 5 EStG transferral, schedule per
        § 33b Abs. 3 Satz 2 EStG.
        """
        child = _child(gdb=80)
        amount = child_disability_pauschbetrag_for_transferral_2025(
            child=child,
            transfer_election_active=True,
        )
        self.assertEqual(amount, Decimal("2120.00"))

    def test_helpless_takes_precedence_over_gdb(self) -> None:
        """``disability_helpless_or_blind=True`` → €7,400 regardless of GdB.

        Authority: § 33b Abs. 3 Satz 3 EStG (erhöhter Pauschbetrag).
        """
        child = _child(gdb=20, helpless_or_blind=True)
        amount = child_disability_pauschbetrag_for_transferral_2025(
            child=child,
            transfer_election_active=True,
        )
        self.assertEqual(amount, Decimal("7400.00"))


class AggregatorTest(unittest.TestCase):
    """``aggregate_germany_children_facts_2025`` — sum across children.

    Authority: § 33b Abs. 5 EStG (transferral); aggregation at the
    Pipeline 1 boundary so the Pipeline 2 stages consume a single
    typed value.
    """

    def test_two_children_with_distinct_pauschbetrags_sum(self) -> None:
        """1 child @ GdB 50 + 1 child hilflos → €1,140 + €7,400 = €8,540.

        Authority: § 33b Abs. 5 EStG sums per-child amounts when both
        children's Pauschbeträge are transferred.
        """
        children = (
            _child(child_id="c-50", gdb=50),
            _child(child_id="c-helpless", gdb=0, helpless_or_blind=True),
        )
        agg = aggregate_germany_children_facts_2025(
            children,
            filing_posture="single",
            disability_pauschbetrag_transfer_election=True,
        )
        self.assertEqual(
            agg.disability_pauschbetrag_total_transferred_eur,
            Decimal("8540.00"),
        )
        self.assertEqual(agg.children_count, 2)

    def test_single_child_at_gdb_80(self) -> None:
        """1 child @ GdB 80 → €2,120 transferred when election active.

        Authority: § 33b Abs. 3 Satz 2 EStG schedule (GdB 80 = €2,120),
        § 33b Abs. 5 EStG transferral.
        """
        children = (_child(gdb=80),)
        agg = aggregate_germany_children_facts_2025(
            children,
            filing_posture="single",
            disability_pauschbetrag_transfer_election=True,
        )
        self.assertEqual(
            agg.disability_pauschbetrag_total_transferred_eur,
            Decimal("2120.00"),
        )

    def test_election_false_yields_zero(self) -> None:
        """Election=false → Pauschbetrag forfeit per § 33b Abs. 5 Satz 1 EStG."""
        children = (_child(gdb=80),)
        agg = aggregate_germany_children_facts_2025(
            children,
            filing_posture="single",
            disability_pauschbetrag_transfer_election=False,
        )
        self.assertEqual(
            agg.disability_pauschbetrag_total_transferred_eur,
            Decimal("0.00"),
        )

    def test_qualifying_relative_excluded(self) -> None:
        """Non-qualifying-child rows do not contribute (§ 33b Abs. 5 EStG)."""
        children = (
            _child(child_id="qr", gdb=80, relationship="qualifying_relative"),
        )
        agg = aggregate_germany_children_facts_2025(
            children,
            filing_posture="single",
            disability_pauschbetrag_transfer_election=True,
        )
        self.assertEqual(
            agg.disability_pauschbetrag_total_transferred_eur,
            Decimal("0.00"),
        )


class DerivePipeline1Test(unittest.TestCase):
    """``derive_de25_children`` — § 33b Abs. 5 EStG fail-closed gate."""

    def test_fail_closed_when_gdb_present_and_election_missing(self) -> None:
        """GdB > 0 child with no election → NotImplementedError.

        Authority: § 33b Abs. 5 EStG transferral requires an explicit
        parents' claim; the engine refuses to silently choose between
        transferral and forfeiture (CLAUDE.md fail-closed posture).
        """
        facts = {
            CHILDREN_INPUT_RAW_KEY: (_child(gdb=80),),
            CHILDREN_INPUT_FILING_POSTURE_KEY: "single",
            CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY: None,
        }
        with self.assertRaises(NotImplementedError) as ctx:
            derive_de25_children(facts)
        # Cite the section in the error message so operators get a
        # legal pointer (per CLAUDE.md fail-closed contract).
        self.assertIn("§ 33b Abs. 5 EStG", str(ctx.exception))

    def test_fail_closed_for_helpless_child_without_election(self) -> None:
        """Hilflos child with no election → NotImplementedError.

        Authority: § 33b Abs. 3 Satz 3 EStG attaches the erhöhter
        Pauschbetrag even at GdB 0; the transferral gate must catch it.
        """
        facts = {
            CHILDREN_INPUT_RAW_KEY: (
                _child(gdb=0, helpless_or_blind=True),
            ),
            CHILDREN_INPUT_FILING_POSTURE_KEY: "single",
            CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY: None,
        }
        with self.assertRaises(NotImplementedError):
            derive_de25_children(facts)

    def test_election_false_with_gdb_yields_zero_transfer(self) -> None:
        """Explicit election=False with GdB child → no transferral.

        Authority: § 33b Abs. 5 Satz 1 EStG forfeit branch.
        """
        facts = {
            CHILDREN_INPUT_RAW_KEY: (_child(gdb=80),),
            CHILDREN_INPUT_FILING_POSTURE_KEY: "single",
            CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY: False,
        }
        result = derive_de25_children(facts)
        self.assertEqual(
            result[CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL],
            Decimal("0.00"),
        )

    def test_election_true_with_gdb_aggregates_total(self) -> None:
        """Election=True with one GdB-80 child → €2,120 transferred.

        Authority: § 33b Abs. 5 EStG, schedule per § 33b Abs. 3 Satz 2 EStG.
        """
        facts = {
            CHILDREN_INPUT_RAW_KEY: (_child(gdb=80),),
            CHILDREN_INPUT_FILING_POSTURE_KEY: "single",
            CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY: True,
        }
        result = derive_de25_children(facts)
        self.assertEqual(
            result[CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL],
            Decimal("2120.00"),
        )

    def test_no_disability_no_election_is_safe(self) -> None:
        """Children with disability_gdb=0 and no election → safe path.

        Authority: § 33b Abs. 5 EStG only attaches when there's a
        Pauschbetrag to transfer; bare children require no election.
        """
        facts = {
            CHILDREN_INPUT_RAW_KEY: (_child(gdb=0),),
            CHILDREN_INPUT_FILING_POSTURE_KEY: "single",
            CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY: None,
        }
        result = derive_de25_children(facts)
        self.assertEqual(
            result[CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL],
            Decimal("0.00"),
        )


class ChildrenSubgraphRuleTest(unittest.TestCase):
    """``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` audit-stage rule body.

    Authority: § 33b Abs. 5 EStG. The Pipeline 2 children sub-graph
    stage re-emits the Pipeline 1 derived total for audit.
    """

    def test_election_active_emits_derived_total(self) -> None:
        """Election=True + children → re-emit the Pipeline 1 total."""
        facts = {
            "de.derived.children_present": True,
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("2120.00"),
            "de.derived.children_disability_pauschbetrag_transfer_election": True,
        }
        out = de25_children_disability_pauschbetrag(facts)
        self.assertEqual(
            out["de.children.disability_pauschbetrag_transferred_eur"],
            Decimal("2120.00"),
        )

    def test_election_false_emits_zero(self) -> None:
        """Election=False → emit zero per § 33b Abs. 5 Satz 1 EStG."""
        facts = {
            "de.derived.children_present": True,
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("2120.00"),
            "de.derived.children_disability_pauschbetrag_transfer_election": False,
        }
        out = de25_children_disability_pauschbetrag(facts)
        self.assertEqual(
            out["de.children.disability_pauschbetrag_transferred_eur"],
            Decimal("0.00"),
        )

    def test_no_children_emits_zero(self) -> None:
        """children_present=False → emit zero (no child Pauschbetrag exists)."""
        facts = {
            "de.derived.children_present": False,
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("0.00"),
            "de.derived.children_disability_pauschbetrag_transfer_election": True,
        }
        out = de25_children_disability_pauschbetrag(facts)
        self.assertEqual(
            out["de.children.disability_pauschbetrag_transferred_eur"],
            Decimal("0.00"),
        )

    def test_executor_runs_through_declared_inputs(self) -> None:
        """Stage runs through the executor (declared inputs only) → invariants I7/I8.

        Authority: § 33b Abs. 5 EStG. The executor enforces input/output
        declarations per CLAUDE.md invariants I7 (rules read only
        declared input_fact_keys) and I8 (rules write only declared
        output_keys).
        """
        # Provide all keys consumed by both children sub-graph stages.
        initial_facts = {
            # DE25-CHILDREN-CREDITS inputs
            "de.derived.children_present": False,
            "de.derived.children_count": 0,
            "de.derived.kinderfreibetrag_total_eur": Decimal("0.00"),
            "de.derived.kindergeld_received_total_eur": Decimal("0.00"),
            "de.ordinary.taxable_income_eur": Decimal("50000"),
            "de.ordinary.income_tax_eur": Decimal("11343"),
            "de.ordinary.filing_posture": "single",
            # DE25-CHILDREN-DISABILITY-PAUSCHBETRAG inputs
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("0.00"),
            "de.derived.children_disability_pauschbetrag_transfer_election": False,
        }
        execution = execute_rule_graph(
            initial_facts, germany_children_law_rules_2025()
        )
        self.assertEqual(
            execution.final_facts[
                "de.children.disability_pauschbetrag_transferred_eur"
            ],
            Decimal("0.00"),
        )


class OrdinaryConsumptionTest(unittest.TestCase):
    """``de25_behinderung_pauschbetrag`` adds the child transferral total.

    Authority: § 33b Abs. 5 Satz 2 EStG — the transferred amount
    attaches to the parents' assessment under the same § 2 Abs. 5 EStG
    ordering as their own Pauschbetrag.
    """

    def _person(self, *, gdb: int = 0, hilflos: bool = False) -> Any:
        # Lightweight stand-in: ``de25_behinderung_pauschbetrag`` reads
        # ``person.gdb`` and ``person.hilflos_or_blind`` only.
        from types import SimpleNamespace

        return SimpleNamespace(gdb=gdb, hilflos_or_blind=hilflos)

    def test_parents_only_when_no_child_transfer(self) -> None:
        """Zero transferral → household total = sum of per-spouse amounts.

        Authority: § 33b Abs. 3 EStG schedule per spouse.
        """
        facts = {
            "de.ordinary.people": (self._person(gdb=50),),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("0.00"),
            # § 33b Abs. 5 Satz 3 EStG split override; ``None`` is the
            # statutory 50/50 default (irrelevant when transferred=0).
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)["de.ordinary.behinderung_pauschbetrag"]
        self.assertEqual(out["total_eur"], Decimal("1140.00"))
        self.assertEqual(out["parents_only_total_eur"], Decimal("1140.00"))
        self.assertEqual(out["child_transferred_eur"], Decimal("0.00"))

    def test_parents_plus_child_transfer_sum(self) -> None:
        """§ 33b Abs. 5 EStG: parents' total + child transferral.

        Parent at GdB 50 (€1,140) plus a child transferral of €2,120 →
        household total €3,260, all flowing through DE25-07 zvE.
        """
        facts = {
            "de.ordinary.people": (self._person(gdb=50),),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("2120.00"),
            # Single-person household — split shape (1.0,) under
            # § 33b Abs. 5 Satz 3 EStG default (no spouse to share with).
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)["de.ordinary.behinderung_pauschbetrag"]
        self.assertEqual(out["total_eur"], Decimal("3260.00"))
        self.assertEqual(out["parents_only_total_eur"], Decimal("1140.00"))
        self.assertEqual(out["child_transferred_eur"], Decimal("2120.00"))

    def test_zero_parents_with_child_transfer(self) -> None:
        """Parents have no GdB; only the child transferral lands.

        Authority: § 33b Abs. 5 EStG (transferred amount attaches to
        the parents' assessment standalone of any parent disability).
        """
        facts = {
            "de.ordinary.people": (self._person(gdb=0),),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal("7400.00"),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)["de.ordinary.behinderung_pauschbetrag"]
        self.assertEqual(out["total_eur"], Decimal("7400.00"))
        self.assertEqual(out["parents_only_total_eur"], Decimal("0.00"))
        self.assertEqual(out["child_transferred_eur"], Decimal("7400.00"))


class EndToEndOrdinaryAssessmentTest(unittest.TestCase):
    """End-to-end: § 33b Abs. 5 EStG transferral reduces zvE → reduces tax.

    Authority: § 33b Abs. 5 Satz 2 EStG attaches the transferred amount
    to the parents' assessment under § 2 Abs. 5 EStG ordering, so the
    Pauschbetrag reduces zvE before § 32a EStG runs. Asserts the final
    tariff drops by approximately ``transferred * marginal_rate``.
    """

    def _build_inputs(self) -> "JointOrdinaryInputs2025":
        from tax_pipeline.y2025.germany_law import (
            JointOrdinaryInputs2025,
            PersonOrdinaryInputs2025,
            WageFacts2025,
        )
        wage = WageFacts2025(
            owner="person_1",
            source_files=("synthetic.pdf",),
            gross_wage_eur=Decimal("100000.00"),
            withheld_wage_tax_eur=Decimal("25000.00"),
            withheld_solidarity_surcharge_eur=Decimal("0.00"),
            multiannual_wage_eur=Decimal("0.00"),
            employer_pension_contribution_eur=Decimal("0.00"),
            employee_pension_contribution_eur=Decimal("0.00"),
            employee_health_insurance_eur=Decimal("0.00"),
            employee_nursing_care_insurance_eur=Decimal("0.00"),
            employee_unemployment_insurance_eur=Decimal("0.00"),
        )
        person = PersonOrdinaryInputs2025(
            slot="person_1",
            order_label="Person 1",
            display_name="Person 1",
            owner="person_1",
            wage=wage,
            work_equipment_items=(),
            home_office_days_without_visit=0,
            home_office_days_with_visit=0,
            manual_work_equipment_deduction_eur=Decimal("0.00"),
            telecom_deduction_eur=Decimal("0.00"),
            employment_legal_insurance_deduction_eur=Decimal("0.00"),
            cross_border_tax_help_deduction_eur=Decimal("0.00"),
            health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
        )
        return JointOrdinaryInputs2025(
            people=(person,),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )

    def test_zero_transferral_reproduces_baseline_zve(self) -> None:
        """Default zero transferral keeps the zvE/tax exactly as-is.

        Authority: backward-compatibility guarantee — the keyword
        argument's default of ``Decimal('0.00')`` must not change
        any pre-Gap-2 numerics.
        """
        from tax_pipeline.y2025.germany_law import compute_joint_ordinary_assessment_2025

        inputs = self._build_inputs()
        baseline = compute_joint_ordinary_assessment_2025(inputs)
        explicit_zero = compute_joint_ordinary_assessment_2025(
            inputs,
            children_disability_pauschbetrag_total_eur=Decimal("0.00"),
        )
        self.assertEqual(
            baseline.joint_taxable_income_eur,
            explicit_zero.joint_taxable_income_eur,
        )
        self.assertEqual(
            baseline.joint_income_tax_eur,
            explicit_zero.joint_income_tax_eur,
        )

    def test_one_child_at_gdb_80_reduces_tax_at_marginal_rate(self) -> None:
        """1 child @ GdB 80 → zvE drops by €2,120; tax drops at 42% marginal rate.

        Authority: § 33b Abs. 5 EStG attaches the €2,120 Pauschbetrag
        to zvE; § 32a Abs. 1 EStG top-bracket rate (42%) applies above
        €68,480, so the tariff differential equals 0.42 × €2,120 = €890.
        Anchored to the 2025 BMF Programmablaufplan.
        """
        from tax_pipeline.y2025.germany_law import (
            compute_joint_ordinary_assessment_2025,
            german_income_tax_single_2025,
        )

        inputs = self._build_inputs()
        baseline = compute_joint_ordinary_assessment_2025(inputs)
        with_child_transfer = compute_joint_ordinary_assessment_2025(
            inputs,
            children_disability_pauschbetrag_total_eur=Decimal("2120.00"),
        )

        # Anchor: the zvE drops by exactly €2,120 (the full Pauschbetrag).
        zve_delta = (
            baseline.joint_taxable_income_eur
            - with_child_transfer.joint_taxable_income_eur
        )
        self.assertEqual(zve_delta, Decimal("2120.00"))

        # Anchor: the tariff drops by exactly the §-32a difference.
        tariff_delta = (
            baseline.joint_income_tax_eur
            - with_child_transfer.joint_income_tax_eur
        )
        expected_tariff_delta = (
            german_income_tax_single_2025(baseline.joint_taxable_income_eur)
            - german_income_tax_single_2025(
                with_child_transfer.joint_taxable_income_eur
            )
        )
        self.assertEqual(tariff_delta, expected_tariff_delta)
        # Sanity-check: at this income level the tariff diff is around
        # the 42 % top-bracket marginal rate × €2,120 ≈ €890 (within
        # rounding).
        self.assertGreater(tariff_delta, Decimal("800"))
        self.assertLess(tariff_delta, Decimal("1000"))


class MFSTransferralAllocationTest(unittest.TestCase):
    """§ 33b Abs. 5 Satz 3 EStG — split between parents under MFS.

    Authority: § 33b Abs. 5 Satz 3 EStG —
        "Der einem Kind zustehende Pauschbetrag … wird auf die Elternteile
        zu gleichen Teilen aufgeteilt, es sei denn, sie beantragen
        gemeinsam eine andere Aufteilung."
    Default 50/50 split between parents; the joint-election clause permits
    a different allocation. Anlage Kind 2025 Zeile 66 captures the
    override percentage; an empty Zeile 66 means the statutory default
    applies.

    Anlage Kind 2025 form lines (BMF Steuerformular):
    - Zeile 64-65: certificate data + qualification statements
    - Zeile 66: optional alternative percentage allocation between
      parents (statutory default 50/50)
    Source confirmation: Helfer in Steuersachen 2.9.0 Zeilen 64-66
    "Übertragung des Pauschbetrags für Kinder mit Behinderung".

    https://www.gesetze-im-internet.de/estg/__33b.html
    """

    def _person(self, *, gdb: int = 0, hilflos: bool = False) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(gdb=gdb, hilflos_or_blind=hilflos)

    def test_married_separate_default_50_50_split_per_satz_3(self) -> None:
        """MFS, 1 child @ GdB 80 → each parent gets €1,060 (50/50 default).

        Authority: § 33b Abs. 5 Satz 3 EStG —
        "wird auf die Elternteile zu gleichen Teilen aufgeteilt".
        With no override (Anlage Kind 2025 Zeile 66 left blank) each
        parent receives 50% of the €2,120 transferral total.
        """
        facts = {
            "de.ordinary.people": (
                self._person(gdb=0),
                self._person(gdb=0),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                "2120.00"
            ),
            # No split override → statutory 50/50 default per
            # § 33b Abs. 5 Satz 3 EStG.
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("2120.00"))
        self.assertEqual(out["parents_only_total_eur"], Decimal("0.00"))
        self.assertEqual(out["child_transferred_eur"], Decimal("2120.00"))
        # 50/50 split — both parents end up with €1,060 of the per-person
        # allocation each (purely from the child transferral, since both
        # parents have GdB 0 themselves).
        self.assertEqual(out["by_person"][0], Decimal("1060.00"))
        self.assertEqual(out["by_person"][1], Decimal("1060.00"))
        # Sum invariant — household total exactly equals the sum of the
        # per-person allocations.
        self.assertEqual(
            sum(out["by_person"], Decimal("0.00")),
            out["total_eur"],
        )

    def test_married_separate_explicit_split_override(self) -> None:
        """MFS, explicit 70/30 split override → €1,484 / €636.

        Authority: § 33b Abs. 5 Satz 3 EStG joint-election clause —
        "es sei denn, sie beantragen gemeinsam eine andere Aufteilung".
        Anlage Kind 2025 Zeile 66 captures the override; here
        70 % to parent[0] and 30 % to parent[1].
        """
        facts = {
            "de.ordinary.people": (
                self._person(gdb=0),
                self._person(gdb=0),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                "2120.00"
            ),
            "de.profile.disability_pauschbetrag_transfer_split": (
                Decimal("0.70"),
                Decimal("0.30"),
            ),
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("2120.00"))
        # 0.70 * 2120 = 1484.00; 0.30 * 2120 = 636.00.
        self.assertEqual(out["by_person"][0], Decimal("1484.00"))
        self.assertEqual(out["by_person"][1], Decimal("636.00"))
        self.assertEqual(
            sum(out["by_person"], Decimal("0.00")),
            out["total_eur"],
        )

    def test_married_separate_invalid_split_fails_closed(self) -> None:
        """Invalid split shape → ValueError citing the joint-election clause.

        Authority: § 33b Abs. 5 Satz 3 EStG requires the joint election
        to specify a valid allocation; the engine refuses to silently
        fall through on a malformed override (CLAUDE.md fail-closed
        contract).
        """
        people = (self._person(gdb=0), self._person(gdb=0))
        # Sum != 1.0 → reject.
        with self.assertRaises(ValueError) as ctx:
            de25_behinderung_pauschbetrag(
                {
                    "de.ordinary.people": people,
                    "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                        "2120.00"
                    ),
                    "de.profile.disability_pauschbetrag_transfer_split": (
                        Decimal("0.70"),
                        Decimal("0.40"),
                    ),
                }
            )
        self.assertIn("§ 33b Abs. 5 Satz 3 EStG", str(ctx.exception))
        # Negative share → reject.
        with self.assertRaises(ValueError):
            de25_behinderung_pauschbetrag(
                {
                    "de.ordinary.people": people,
                    "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                        "2120.00"
                    ),
                    "de.profile.disability_pauschbetrag_transfer_split": (
                        Decimal("1.50"),
                        Decimal("-0.50"),
                    ),
                }
            )
        # Wrong number of entries (does not match person count) → reject.
        with self.assertRaises(ValueError):
            de25_behinderung_pauschbetrag(
                {
                    "de.ordinary.people": people,
                    "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                        "2120.00"
                    ),
                    "de.profile.disability_pauschbetrag_transfer_split": (
                        Decimal("1.00"),
                    ),
                }
            )

    def test_married_separate_split_zero_for_zero_children_is_zero(self) -> None:
        """No qualifying child Pauschbetrag → both parents get 0; no error.

        Authority: § 33b Abs. 5 Satz 3 EStG only applies once a child
        Pauschbetrag exists to allocate. The fail-closed gate on the
        split override only fires when ``children_transferred_total > 0``;
        a zero-transferral household with a missing/None split is the
        normal demo posture and must not raise.
        """
        facts = {
            "de.ordinary.people": (
                self._person(gdb=0),
                self._person(gdb=0),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                "0.00"
            ),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("0.00"))
        self.assertEqual(out["by_person"][0], Decimal("0.00"))
        self.assertEqual(out["by_person"][1], Decimal("0.00"))

    def test_single_filer_full_to_sole_parent(self) -> None:
        """Single filer, 1 child @ GdB 80 → sole parent gets full €2,120.

        Authority: § 33b Abs. 5 Satz 3 EStG presupposes two parents to
        split between; a single-parent household has no split posture
        and the full transferred amount lands on the only person.
        """
        facts = {
            "de.ordinary.people": (self._person(gdb=0),),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                "2120.00"
            ),
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        self.assertEqual(out["total_eur"], Decimal("2120.00"))
        self.assertEqual(out["by_person"][0], Decimal("2120.00"))
        self.assertEqual(
            sum(out["by_person"], Decimal("0.00")),
            out["total_eur"],
        )

    def test_married_joint_full_to_household_no_split_needed(self) -> None:
        """MFJ, 1 child @ GdB 80 → household total €2,120 (one assessment).

        Authority: § 26b EStG joint assessment treats the spouses as a
        single taxpayer; per § 33b Abs. 5 Satz 3 EStG the split between
        parents is moot because there is only one zvE. The per-person
        allocation collapses into the joint base regardless of how it
        is distributed.
        """
        facts = {
            "de.ordinary.people": (
                self._person(gdb=0),
                self._person(gdb=0),
            ),
            "de.derived.children_disability_pauschbetrag_total_eur": Decimal(
                "2120.00"
            ),
            # MFJ profiles surface ``None`` because Anlage Kind Zeile 66
            # is irrelevant under joint assessment; we still expect the
            # 50/50 default to apply at the per-person trace level.
            "de.profile.disability_pauschbetrag_transfer_split": None,
        }
        out = de25_behinderung_pauschbetrag(facts)[
            "de.ordinary.behinderung_pauschbetrag"
        ]
        # The household total is the legally effective number — the joint
        # assessment uses one zvE so the per-person trace is a bookkeeping
        # detail, but the sum-invariant must hold.
        self.assertEqual(out["total_eur"], Decimal("2120.00"))
        self.assertEqual(
            sum(out["by_person"], Decimal("0.00")),
            out["total_eur"],
        )


class AnlageKindFormLineRenderingTest(unittest.TestCase):
    """§ 33b Abs. 5 EStG transferral lands on Anlage Kind Zeilen 64-66.

    Authority: § 33b Abs. 5 EStG; Anlage Kind 2025 BMF Steuerformular —
    Zeilen 64-66 carry "Übertragung des Pauschbetrags für Kinder mit
    Behinderung". The bidirectional invariant I3 requires every form
    line the renderer touches to match an
    ``OutputDeclaration.form_line_refs`` entry on the rule graph; this
    test asserts that the children disability stage's
    ``form_line_refs`` declares Zeile 65 (the canonical Pauschbetrag
    amount line) and that the Anlage Kind renderer emits a
    matching read.

    Source confirmation: Helfer in Steuersachen 2.9.0 Zeilen 64-66
    "Übertragung des Pauschbetrags für Kinder mit Behinderung".
    https://www.gesetze-im-internet.de/estg/__33b.html
    """

    def test_children_disability_stage_declares_anlage_kind_form_line(
        self,
    ) -> None:
        """``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` declares Zeile 65.

        The rule-graph declaration is the audit anchor: the form line
        the parent assessment lands on per Anlage Kind 2025 §-33b-Abs.-5
        block. Without the declaration, the renderer-side write is
        not traceable to a rule output (invariant I3).
        """
        from tax_pipeline.y2025.germany_stages import (
            germany_children_law_stages_2025,
        )

        stage = next(
            stage
            for stage in germany_children_law_stages_2025()
            if stage.stage_id == "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG"
        )
        decl = next(
            d
            for d in stage.outputs
            if d.key == "de.children.disability_pauschbetrag_transferred_eur"
        )
        self.assertTrue(
            decl.form_line_refs,
            "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG must declare Anlage "
            "Kind form_line_refs per § 33b Abs. 5 EStG; without the "
            "declaration invariant I3 cannot tie the rendered Pauschbetrag "
            "transferral on Anlage Kind 2025 Zeile 65 back to a rule "
            "output.",
        )
        forms = {(ref.form, ref.line) for ref in decl.form_line_refs}
        self.assertIn(("Anlage Kind", "65"), forms)
        for ref in decl.form_line_refs:
            self.assertIn("gesetze-im-internet.de/estg/__33b", ref.url)

    def test_anlage_kind_renders_transferred_pauschbetrag(self) -> None:
        """End-to-end demo render writes Anlage Kind with the §-33b transferral.

        The demo workspace has zero qualifying children → the rendered
        amount is €0.00 — but the form must exist and the line must be
        present so the renderer's I3 surface stays anchored even on the
        demo posture.

        Authority: § 33b Abs. 5 EStG transferral surface on Anlage Kind
        2025 Zeile 65 (BMF Steuerformular).
        """
        from tests.generated_demo import generated_demo_paths
        from tax_pipeline.forms.germany import render_germany_forms
        from tax_pipeline.pipelines.y2025.final_legal_output import (
            write_final_legal_output_2025,
        )

        with generated_demo_paths() as paths:
            write_final_legal_output_2025(paths)
            render_germany_forms(paths)
            anlage_kind = (
                paths.germany_forms_root / f"{paths.year}_anlage_kind.md"
            ).read_text(encoding="utf-8")

        # The form file must exist and reference the transferred-Pauschbetrag
        # block at Zeile 65 (canonical 2025 BMF line for the per-child
        # Behinderten-Pauschbetrag amount).
        self.assertIn("Anlage Kind", anlage_kind)
        self.assertIn("Zeile 65", anlage_kind)
        # Demo posture — no qualifying children, so the transferral is
        # zero. The legal-value envelope must still emit a numeric.
        self.assertIn("0.00", anlage_kind)

    def test_anlage_kind_form_line_refs_have_renderer_consumer(self) -> None:
        """Bidirectional invariant I3 — declaration ↔ renderer touch.

        The existing
        ``tests/test_form_renderer_lines_match_output_declarations.py``
        enforces both directions across every German + U.S. + treaty
        stage; this test re-asserts the contract specifically for the
        DE25-CHILDREN-DISABILITY-PAUSCHBETRAG / Anlage Kind binding so
        a regression to ``form_line_refs=()`` (or to a renderer that
        skips Anlage Kind) flags here first with a § 33b citation.

        Authority: invariant I3 (CLAUDE.md) + § 33b Abs. 5 EStG.
        """
        from tests.y_agnostic.test_form_renderer_lines_match_output_declarations import (
            FormRendererLinesMatchOutputDeclarationsTest,
        )

        # Run both halves of the bidirectional invariant. Either failing
        # here is the actionable regression point for the children
        # disability binding.
        suite = unittest.TestSuite(
            [
                FormRendererLinesMatchOutputDeclarationsTest(
                    "test_renderer_reads_match_some_output_declaration"
                ),
                FormRendererLinesMatchOutputDeclarationsTest(
                    "test_output_declaration_form_lines_have_renderer_consumer"
                ),
            ]
        )
        result = unittest.TestResult()
        suite.run(result)
        self.assertTrue(
            result.wasSuccessful(),
            "I3 bidirectional invariant failed; declarations:\n"
            + "\n".join(f"{f[0].id()}: {f[1]}" for f in result.failures)
            + "\n".join(f"{e[0].id()}: {e[1]}" for e in result.errors),
        )


class NarrativeTemplateTest(unittest.TestCase):
    """``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG.jinja`` bilingual narrative.

    Authority: § 33b Abs. 3 EStG (Pauschbetrag schedule) +
    § 33b Abs. 5 EStG (transferral) + § 33b Abs. 5 Satz 3 EStG (50/50
    default split, joint-election override) + BGBl. I 2020 S. 2770
    (Behinderten-Pauschbetragsgesetz, doubled rates effective 2021).
    https://www.gesetze-im-internet.de/estg/__33b.html
    """

    def _packet(self, *, language: str) -> Any:
        from tax_pipeline.core.narrative import (
            NarrativeFormLine,
            NarrativeMathStep,
            NarrativeValue,
            RuleNarrative,
        )

        return RuleNarrative(
            rule_id="DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
            country="DE",
            language=language,
            template_id="DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
            title="§ 33b Abs. 5 EStG transferral of a child's Behinderten-Pauschbetrag",
            legal_refs=(
                "§ 33b Abs. 3 EStG",
                "§ 33b Abs. 5 EStG",
                "§ 33b Abs. 5 Satz 3 EStG",
                "BGBl. I 2020 S. 2770",
            ),
            authority_urls=(
                "https://www.gesetze-im-internet.de/estg/__33b.html",
                "https://www.gesetze-im-internet.de/estg/__33b.html",
                "https://www.gesetze-im-internet.de/estg/__33b.html",
                "https://www.gesetze-im-internet.de/bgbl_i_2020/2770.html",
            ),
            inputs=(
                NarrativeValue(
                    "Pipeline 1 derived total",
                    "2120.00 EUR",
                    "de.derived.children_disability_pauschbetrag_total_eur",
                ),
                NarrativeValue(
                    "Election active",
                    "True",
                    "de.derived.children_disability_pauschbetrag_transfer_election",
                ),
                NarrativeValue(
                    "Children present",
                    "True",
                    "de.derived.children_present",
                ),
            ),
            math_steps=(
                NarrativeMathStep(
                    "Re-emit the § 33b Abs. 5 EStG transferral total for audit",
                    "de.children.disability_pauschbetrag_transferred_eur = "
                    "de.derived.children_disability_pauschbetrag_total_eur "
                    "when election=True and children_present, else 0",
                    "2120.00 EUR",
                ),
            ),
            outputs=(
                NarrativeValue(
                    "Transferred Pauschbetrag",
                    "2120.00 EUR",
                    "de.children.disability_pauschbetrag_transferred_eur",
                ),
            ),
            form_lines=(
                NarrativeFormLine(
                    "Anlage Kind",
                    "Zeile 65",
                    "2120.00 EUR",
                ),
            ),
        )

    def _render(self, *, language: str) -> str:
        from tax_pipeline.narrative.render import (
            DEFAULT_TEMPLATE_ROOT,
            render_narrative_markdown,
        )

        return render_narrative_markdown(
            (self._packet(language=language),),
            template_root=DEFAULT_TEMPLATE_ROOT,
            title="Germany",
        )

    def test_template_exists(self) -> None:
        """Template file lives under the canonical template root.

        Authority: CLAUDE.md tax-rule narrative requirement —
        "Jinja narrative templates must be named by jurisdiction and
        rule, and must match the same law citation used by the core
        function and tests."
        """
        from tax_pipeline.narrative.render import DEFAULT_TEMPLATE_ROOT

        path = (
            DEFAULT_TEMPLATE_ROOT
            / "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG.jinja"
        )
        self.assertTrue(
            path.exists(),
            "Narrative template DE25-CHILDREN-DISABILITY-PAUSCHBETRAG.jinja "
            "is required to satisfy the CLAUDE.md narrative-template "
            "naming rule for § 33b Abs. 5 EStG.",
        )

    def test_renders_bilingual_with_required_authorities_and_amount(
        self,
    ) -> None:
        """Render asserts § 33b citations + the EUR amount in both languages.

        Authority: § 33b Abs. 3 + Abs. 5 + Abs. 5 Satz 3 EStG and
        BGBl. I 2020 S. 2770 must all appear so the audit reader can
        cross-check the rule body's citations against the rendered
        narrative.
        """
        de = self._render(language="de")
        en = self._render(language="en")

        for rendered in (de, en):
            self.assertIn("§ 33b Abs. 3 EStG", rendered)
            self.assertIn("§ 33b Abs. 5 EStG", rendered)
            self.assertIn("BGBl. I 2020 S. 2770", rendered)
            self.assertIn(
                "https://www.gesetze-im-internet.de/estg/__33b.html",
                rendered,
            )

        # The DE block renders the EUR amount in German locale
        # ("2.120,00 EUR") via an inline thousand/decimal swap of the
        # English ``money`` filter output; the EN block leaves the
        # money filter's English locale formatting in place
        # ("2,120.00 EUR"). Both blocks pin the same Decimal scalar.
        self.assertIn("2.120,00", de)
        self.assertIn("2,120.00", en)

        # The Satz-3 split clause is the new architectural addition.
        self.assertIn("§ 33b Abs. 5 Satz 3 EStG", de)
        self.assertIn("§ 33b Abs. 5 Satz 3 EStG", en)

        # Form-line footer points to the BMF 2025 Anlage Kind Zeile.
        self.assertIn("Anlage Kind", de)
        self.assertIn("Anlage Kind", en)
        self.assertIn("65", de)
        self.assertIn("65", en)


if __name__ == "__main__":
    unittest.main()
