"""Tests for § 31 EStG Familienleistungsausgleich Günstigerprüfung — Wave 11A.

The DE25-CHILDREN-CREDITS rule body and stage declared here implement
the better-of comparison between the § 32 Abs. 6 EStG Kinderfreibetrag
+ BEA-Freibetrag deduction and the BKGG § 6 Abs. 2 Kindergeld actually
paid out for the household. The selected arm becomes the
``de.children.applied_relief_eur`` legal output.

Authority:
- § 31 EStG (Familienleistungsausgleich, Günstigerprüfung):
  https://www.gesetze-im-internet.de/estg/__31.html
- § 32 Abs. 6 EStG (Kinderfreibetrag + BEA-Freibetrag — €6,672 + €2,928
  = €9,600 combined per child for 2025):
  https://www.gesetze-im-internet.de/estg/__32.html
- BKGG § 6 Abs. 2 (Kindergeld €250/month per child since 2023):
  https://www.gesetze-im-internet.de/bkgg_1996/__6.html
- § 32a Abs. 1 / Abs. 5 EStG (basic / splitting tariff used for the
  counterfactual zvE):
  https://www.gesetze-im-internet.de/estg/__32a.html

Each test asserts a concrete EUR amount derived from the official 2025
§ 32a EStG tariff (BMF Programmablaufplan 2025) applied to the
counterfactual zvE.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from typing import Any

from tax_pipeline.core.stages import execute_rule_graph
from tax_pipeline.y2025.germany_law import (
    Child2025,
    GermanyChildrenFacts2025,
    aggregate_germany_children_facts_2025,
    german_income_tax_single_2025,
    german_income_tax_split_2025,
    q2,
)
from tax_pipeline.y2025.germany_children_rules import (
    de25_children_credits,
    germany_children_law_rules_2025,
)


def _child(
    *,
    child_id: str = "child-1",
    months: int = 12,
    recipient: str = "taxpayer",
    relationship: str = "qualifying_child",
) -> Child2025:
    """Construct a synthetic Child2025 covering the columns the German
    Familienleistungsausgleich aggregator reads.

    Authority: § 32 Abs. 6 EStG (qualifying child definition) and BKGG
    § 6 Abs. 2 (Kindergeld monthly accrual).
    """
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
        kindergeld_received_eur=Decimal("255.00") * Decimal(months)
        if recipient in {"taxpayer", "spouse"}
        else Decimal("0.00"),
        kindergeld_recipient=recipient,
        disability_gdb=0,
    )


def _build_facts(
    *,
    children_facts: GermanyChildrenFacts2025,
    posture: str,
    joint_zve_eur: Decimal,
    joint_income_tax_eur: Decimal,
) -> dict[str, Any]:
    """Construct the minimum facts dict the DE25-CHILDREN-CREDITS rule
    consumes via its declared ``input_fact_keys``.

    Mirrors the four ``de.derived.children_*`` aggregates DE25-CHILDREN-
    CREDITS reads from ``derived-facts.json`` plus the three ordinary
    scalars threaded in by ``germany_children_initial_facts_2025``.
    """
    return {
        "de.derived.children_present": children_facts.children_present,
        "de.derived.children_count": children_facts.children_count,
        "de.derived.kinderfreibetrag_total_eur": (
            children_facts.kinderfreibetrag_total_eur
        ),
        "de.derived.kindergeld_received_total_eur": (
            children_facts.kindergeld_received_total_eur
        ),
        # Gap 2 — § 33b Abs. 5 EStG transferral facts. The kinderfreibetrag
        # tests fix the GdB to 0 in ``_child`` so the transferral total is
        # uniformly zero and the election is irrelevant for these tests;
        # provide both keys so the rule graph executor can satisfy the
        # ``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` declared inputs.
        "de.derived.children_disability_pauschbetrag_total_eur": (
            children_facts.disability_pauschbetrag_total_transferred_eur
        ),
        "de.derived.children_disability_pauschbetrag_transfer_election": False,
        "de.ordinary.taxable_income_eur": joint_zve_eur,
        "de.ordinary.income_tax_eur": joint_income_tax_eur,
        "de.ordinary.filing_posture": posture,
    }


class KinderfreibetragGuenstigerpruefungTest(unittest.TestCase):
    """§ 31 EStG Günstigerprüfung better-of arithmetic.

    Numeric expectations come from the dated 2025 § 32a EStG tariff
    (BMF Programmablaufplan 2025) applied to ``zvE − §-32-Abs.-6-EStG
    Freibetrag`` and compared against BKGG § 6 Abs. 2 Kindergeld.
    """

    def test_no_children_short_circuits_to_zero(self) -> None:
        """0 qualifying children → § 31 EStG short-circuits.

        Authority: § 32 Abs. 6 EStG requires at least one qualifying
        child for the Freibetrag; BKGG § 6 Abs. 2 has nothing to pay.
        Both arms of § 31 EStG are zero so no election occurs.
        """
        children_facts = aggregate_germany_children_facts_2025(
            (), filing_posture="single"
        )
        facts = _build_facts(
            children_facts=children_facts,
            posture="single",
            joint_zve_eur=Decimal("50000"),
            joint_income_tax_eur=Decimal("11343"),
        )
        out = de25_children_credits(facts)
        self.assertEqual(out["de.children.kinderfreibetrag_total_eur"], Decimal("0.00"))
        self.assertEqual(out["de.children.kindergeld_total_eur"], Decimal("0.00"))
        self.assertEqual(
            out["de.children.kinderfreibetrag_tax_saving_eur"], Decimal("0.00")
        )
        self.assertEqual(out["de.children.applied_relief_eur"], Decimal("0.00"))
        self.assertEqual(out["de.children.qualifying_children_count"], 0)
        self.assertEqual(out["de.children.guenstigerpruefung_choice"], "kindergeld")

    def test_one_child_low_income_kindergeld_wins(self) -> None:
        """Single, zvE €30,000, 1 child → § 31 EStG selects Kindergeld.

        Authority:
        - § 32a Abs. 1 EStG basic tariff applied to (zvE − €9,600).
          https://www.gesetze-im-internet.de/estg/__32a.html
        - At a low marginal rate the Freibetrag savings (€2,564) fall
          short of BKGG § 6 Abs. 2 Kindergeld (€3,000), so § 31 EStG
          keeps the Kindergeld.
        """
        # Anchor expected values to the live § 32a EStG tariff so a
        # tariff drift surfaces here rather than in production.
        zve = Decimal("30000")
        actual_tax = german_income_tax_single_2025(zve)
        counterfactual_tax = german_income_tax_single_2025(zve - Decimal("9600"))
        expected_saving = q2(actual_tax - counterfactual_tax)
        # Sanity-check the anchored values.
        self.assertEqual(actual_tax, Decimal("4303"))
        self.assertEqual(counterfactual_tax, Decimal("1739"))
        self.assertEqual(expected_saving, Decimal("2564.00"))

        children_facts = aggregate_germany_children_facts_2025(
            (_child(months=12, recipient="taxpayer"),),
            filing_posture="single",
        )
        facts = _build_facts(
            children_facts=children_facts,
            posture="single",
            joint_zve_eur=zve,
            joint_income_tax_eur=actual_tax,
        )
        out = de25_children_credits(facts)
        self.assertEqual(
            out["de.children.kinderfreibetrag_total_eur"], Decimal("9600.00")
        )
        self.assertEqual(
            out["de.children.kindergeld_total_eur"], Decimal("3060.00")
        )
        self.assertEqual(
            out["de.children.kinderfreibetrag_tax_saving_eur"],
            Decimal("2564.00"),
        )
        self.assertEqual(out["de.children.guenstigerpruefung_choice"], "kindergeld")
        # Kindergeld branch: applied_relief_eur is 0 because Kindergeld
        # is retained outside the assessment (the household already
        # received it during the year via the Familienkasse). The
        # final-stage netting under § 31 Satz 4 EStG only adjusts the
        # refund when Kinderfreibetrag wins.
        self.assertEqual(
            out["de.children.applied_relief_eur"], Decimal("0.00")
        )
        self.assertEqual(out["de.children.qualifying_children_count"], 1)

    def test_one_child_high_income_kinderfreibetrag_wins(self) -> None:
        """Single, zvE €100,000, 1 child → § 31 EStG selects Freibetrag.

        Authority:
        - § 32a Abs. 1 EStG top-bracket marginal rate (42 % over
          €68,480) makes the §-32-Abs.-6-EStG €9,600 deduction worth
          €4,032 in tax, exceeding BKGG § 6 Abs. 2 Kindergeld
          (€3,000). § 31 EStG therefore elects the Freibetrag.
        """
        zve = Decimal("100000")
        actual_tax = german_income_tax_single_2025(zve)
        counterfactual_tax = german_income_tax_single_2025(zve - Decimal("9600"))
        expected_saving = q2(actual_tax - counterfactual_tax)
        self.assertEqual(actual_tax, Decimal("31088"))
        self.assertEqual(counterfactual_tax, Decimal("27056"))
        self.assertEqual(expected_saving, Decimal("4032.00"))

        children_facts = aggregate_germany_children_facts_2025(
            (_child(months=12, recipient="taxpayer"),),
            filing_posture="single",
        )
        facts = _build_facts(
            children_facts=children_facts,
            posture="single",
            joint_zve_eur=zve,
            joint_income_tax_eur=actual_tax,
        )
        out = de25_children_credits(facts)
        self.assertEqual(
            out["de.children.kinderfreibetrag_total_eur"], Decimal("9600.00")
        )
        self.assertEqual(
            out["de.children.kindergeld_total_eur"], Decimal("3060.00")
        )
        self.assertEqual(
            out["de.children.kinderfreibetrag_tax_saving_eur"],
            Decimal("4032.00"),
        )
        self.assertEqual(
            out["de.children.guenstigerpruefung_choice"], "kinderfreibetrag"
        )
        self.assertEqual(
            out["de.children.applied_relief_eur"], Decimal("4032.00")
        )
        self.assertEqual(out["de.children.qualifying_children_count"], 1)

    def test_two_children_scale_linearly(self) -> None:
        """Single, zvE €120,000, 2 children → totals scale linearly.

        Authority:
        - § 32 Abs. 6 EStG: each qualifying child adds €9,600 (combined
          Kinderfreibetrag + BEA-Freibetrag).
        - BKGG § 6 Abs. 2: each qualifying child adds €3,000/year
          (€250 × 12).
        - The Freibetrag tax saving on €19,200 at the 42 % top bracket
          is €8,064, exceeding the €6,000 Kindergeld so § 31 EStG
          elects the Freibetrag.
        """
        zve = Decimal("120000")
        actual_tax = german_income_tax_single_2025(zve)
        counterfactual_tax = german_income_tax_single_2025(zve - Decimal("19200"))
        expected_saving = q2(actual_tax - counterfactual_tax)
        self.assertEqual(actual_tax, Decimal("39488"))
        self.assertEqual(counterfactual_tax, Decimal("31424"))
        self.assertEqual(expected_saving, Decimal("8064.00"))

        children_facts = aggregate_germany_children_facts_2025(
            (
                _child(child_id="child-1", months=12, recipient="taxpayer"),
                _child(child_id="child-2", months=12, recipient="taxpayer"),
            ),
            filing_posture="single",
        )
        facts = _build_facts(
            children_facts=children_facts,
            posture="single",
            joint_zve_eur=zve,
            joint_income_tax_eur=actual_tax,
        )
        out = de25_children_credits(facts)
        # § 32 Abs. 6 EStG: 2 × €9,600 = €19,200 combined Freibetrag.
        self.assertEqual(
            out["de.children.kinderfreibetrag_total_eur"], Decimal("19200.00")
        )
        # BKGG § 6 Abs. 2: 2 × €3,060 = €6,120 (€255/month from 2025).
        self.assertEqual(
            out["de.children.kindergeld_total_eur"], Decimal("6120.00")
        )
        self.assertEqual(
            out["de.children.kinderfreibetrag_tax_saving_eur"],
            Decimal("8064.00"),
        )
        self.assertEqual(
            out["de.children.guenstigerpruefung_choice"], "kinderfreibetrag"
        )
        self.assertEqual(
            out["de.children.applied_relief_eur"], Decimal("8064.00")
        )
        self.assertEqual(out["de.children.qualifying_children_count"], 2)


class KinderfreibetragMarriedJointTest(unittest.TestCase):
    """§ 31 EStG Günstigerprüfung under § 26b / § 32a Abs. 5 EStG splitting.

    Authority: § 26b EStG joint assessment, § 32a Abs. 5 EStG splitting
    tariff applied to the counterfactual zvE.
    """

    def test_married_joint_high_income_kinderfreibetrag_wins(self) -> None:
        """MFJ, zvE €200,000, 1 child → § 31 EStG selects Freibetrag.

        Splitting tariff applied to zvE/2 = €100,000 puts each spouse
        in the 42 % bracket, so the §-32-Abs.-6-EStG €9,600 deduction
        delivers a tariff saving exceeding €3,000 Kindergeld.
        """
        zve = Decimal("200000")
        actual_tax = german_income_tax_split_2025(zve)
        counterfactual_tax = german_income_tax_split_2025(zve - Decimal("9600"))
        expected_saving = q2(actual_tax - counterfactual_tax)
        # Anchor the tariff outputs explicitly so a § 32a Abs. 5 EStG
        # drift surfaces here rather than silently in the rule.
        self.assertEqual(actual_tax, Decimal("62176"))
        self.assertEqual(counterfactual_tax, Decimal("58144"))
        self.assertEqual(expected_saving, Decimal("4032.00"))

        children_facts = aggregate_germany_children_facts_2025(
            (_child(months=12, recipient="taxpayer"),),
            filing_posture="married_joint",
        )
        facts = _build_facts(
            children_facts=children_facts,
            posture="married_joint",
            joint_zve_eur=zve,
            joint_income_tax_eur=actual_tax,
        )
        out = de25_children_credits(facts)
        self.assertEqual(
            out["de.children.kinderfreibetrag_total_eur"], Decimal("9600.00")
        )
        self.assertEqual(
            out["de.children.kindergeld_total_eur"], Decimal("3060.00")
        )
        self.assertEqual(
            out["de.children.kinderfreibetrag_tax_saving_eur"],
            Decimal("4032.00"),
        )
        self.assertEqual(
            out["de.children.guenstigerpruefung_choice"], "kinderfreibetrag"
        )
        self.assertEqual(
            out["de.children.applied_relief_eur"], Decimal("4032.00")
        )


class KinderfreibetragRuleGraphTest(unittest.TestCase):
    """Exercise DE25-CHILDREN-CREDITS through ``execute_rule_graph``.

    Confirms invariant I7 (declared-only input reads) and invariant I8
    (declared-only output writes) hold under the executor's runtime
    tracking machinery.
    """

    def test_runs_through_executor_with_declared_inputs(self) -> None:
        # Authority anchors mirror the ``test_one_child_high_income_*``
        # case so the executor path delivers the same § 31 EStG
        # election as the direct ``calculate`` invocation.
        zve = Decimal("100000")
        actual_tax = german_income_tax_single_2025(zve)
        children_facts = aggregate_germany_children_facts_2025(
            (_child(months=12, recipient="taxpayer"),),
            filing_posture="single",
        )
        initial_facts = _build_facts(
            children_facts=children_facts,
            posture="single",
            joint_zve_eur=zve,
            joint_income_tax_eur=actual_tax,
        )
        execution = execute_rule_graph(
            initial_facts, germany_children_law_rules_2025()
        )
        final = execution.final_facts
        self.assertEqual(
            final["de.children.guenstigerpruefung_choice"], "kinderfreibetrag"
        )
        self.assertEqual(
            final["de.children.applied_relief_eur"], Decimal("4032.00")
        )
        # All declared output_keys must be present in final_facts (I8).
        for key in (
            "de.children.kinderfreibetrag_total_eur",
            "de.children.kindergeld_total_eur",
            "de.children.kinderfreibetrag_tax_saving_eur",
            "de.children.guenstigerpruefung_choice",
            "de.children.applied_relief_eur",
            "de.children.qualifying_children_count",
        ):
            self.assertIn(key, final, f"missing declared output: {key}")


if __name__ == "__main__":
    unittest.main()
