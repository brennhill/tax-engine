"""Tests for § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer.

Authority:
- § 4 Abs. 5 Satz 1 Nr. 6b EStG (https://www.gesetze-im-internet.de/estg/__4.html)
- § 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG (mutual exclusion with Tagespauschale).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR,
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    arbeitszimmer_deductible_2025,
    compute_joint_ordinary_assessment_2025,
)


def _wage(owner: str) -> WageFacts2025:
    return WageFacts2025(
        owner=owner,
        source_files=("synthetic.pdf",),
        gross_wage_eur=Decimal("60000.00"),
        withheld_wage_tax_eur=Decimal("12000.00"),
        withheld_solidarity_surcharge_eur=Decimal("0.00"),
        multiannual_wage_eur=Decimal("0.00"),
        employer_pension_contribution_eur=Decimal("0.00"),
        employee_pension_contribution_eur=Decimal("0.00"),
        employee_health_insurance_eur=Decimal("0.00"),
        employee_nursing_care_insurance_eur=Decimal("0.00"),
        employee_unemployment_insurance_eur=Decimal("0.00"),
    )


def _person(slot: str, *, home_office_days_without_visit: int = 0) -> PersonOrdinaryInputs2025:
    return PersonOrdinaryInputs2025(
        slot=slot,
        order_label=slot.replace("_", " ").title(),
        display_name=slot.replace("_", " ").title(),
        owner=slot,
        wage=_wage(slot),
        work_equipment_items=(),
        home_office_days_without_visit=home_office_days_without_visit,
        home_office_days_with_visit=0,
        manual_work_equipment_deduction_eur=Decimal("0.00"),
        telecom_deduction_eur=Decimal("0.00"),
        employment_legal_insurance_deduction_eur=Decimal("0.00"),
        cross_border_tax_help_deduction_eur=Decimal("0.00"),
        health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
    )


class ArbeitszimmerLawFunctionTest(unittest.TestCase):
    def test_not_claimed_returns_zero(self) -> None:
        self.assertEqual(
            arbeitszimmer_deductible_2025(
                arbeitszimmer_claimed=False,
                qualifies_as_mittelpunkt=True,
                actual_costs_eur=Decimal("5000.00"),
                tagespauschale_days_total=0,
            ),
            Decimal("0.00"),
        )

    def test_mittelpunkt_yields_actual_costs(self) -> None:
        self.assertEqual(
            arbeitszimmer_deductible_2025(
                arbeitszimmer_claimed=True,
                qualifies_as_mittelpunkt=True,
                actual_costs_eur=Decimal("5000.00"),
                tagespauschale_days_total=0,
            ),
            Decimal("5000.00"),
        )

    def test_no_mittelpunkt_yields_jahrespauschale(self) -> None:
        # Jahrespauschale is the fixed €1,260 regardless of actual costs.
        self.assertEqual(
            arbeitszimmer_deductible_2025(
                arbeitszimmer_claimed=True,
                qualifies_as_mittelpunkt=False,
                actual_costs_eur=Decimal("5000.00"),
                tagespauschale_days_total=0,
            ),
            ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR,
        )
        self.assertEqual(ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR, Decimal("1260.00"))

    def test_mutual_exclusion_with_tagespauschale_fails_closed(self) -> None:
        # § 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG forbids combining the
        # Jahrespauschale (Nr. 6b) with the Tagespauschale (Nr. 6c).
        with self.assertRaisesRegex(ValueError, "Tagespauschale"):
            arbeitszimmer_deductible_2025(
                arbeitszimmer_claimed=True,
                qualifies_as_mittelpunkt=False,
                actual_costs_eur=Decimal("0.00"),
                tagespauschale_days_total=10,
            )


class ArbeitszimmerStageIntegrationTest(unittest.TestCase):
    def test_demo_workspace_zero_default_keeps_baseline_zve(self) -> None:
        from tests.generated_demo import generated_demo_paths
        from tax_pipeline.y2025.germany_inputs import load_joint_ordinary_inputs_2025
        from tax_pipeline.y2025.germany_ordinary_rules import (
            execute_germany_ordinary_rule_graph,
            germany_ordinary_initial_facts_2025,
            germany_ordinary_initial_fingerprints_2025,
        )

        with generated_demo_paths() as paths:
            inputs = load_joint_ordinary_inputs_2025(paths)
            initial = germany_ordinary_initial_facts_2025(inputs)
            execution = execute_germany_ordinary_rule_graph(
                initial,
                input_fingerprints=germany_ordinary_initial_fingerprints_2025(initial),
            )
            self.assertEqual(
                execution.final_facts["de.ordinary.arbeitszimmer"]["deductible_eur"],
                Decimal("0.00"),
            )

    def test_mittelpunkt_with_actual_costs_reduces_zve(self) -> None:
        # Single, wage 60000 → werb 1230 → net 58770. Sonderausgaben 36.
        # Mittelpunkt + actual costs 5000 → arbeitszimmer = 5000.
        # zvE = 58770 - 36 - 5000 = 53734.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            arbeitszimmer_claimed=True,
            arbeitszimmer_qualifies_as_mittelpunkt=True,
            arbeitszimmer_actual_costs_eur=Decimal("5000.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("53734.00"))

    def test_no_mittelpunkt_with_pauschale_reduces_zve(self) -> None:
        # Single, no Mittelpunkt → 1260 EUR Pauschale. zvE = 58734 - 1260 = 57474.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            arbeitszimmer_claimed=True,
            arbeitszimmer_qualifies_as_mittelpunkt=False,
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("57474.00"))

    def test_tagespauschale_collision_fails_closed(self) -> None:
        # Person 1 claims 10 home-office days under § 4 Abs. 5 Satz 1
        # Nr. 6c (Tagespauschale, modeled in DE25-02). Claiming the
        # § 4 Abs. 5 Satz 1 Nr. 6b Pauschale on top must fail closed
        # under Satz 3 of Nr. 6c.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1", home_office_days_without_visit=10),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            arbeitszimmer_claimed=True,
            arbeitszimmer_qualifies_as_mittelpunkt=False,
        )
        with self.assertRaisesRegex(ValueError, "Tagespauschale"):
            compute_joint_ordinary_assessment_2025(inputs)

    def test_zero_claimed_keeps_zve(self) -> None:
        # Default behavior: arbeitszimmer_claimed=False → 0 deduction.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("58734.00"))


if __name__ == "__main__":
    unittest.main()
