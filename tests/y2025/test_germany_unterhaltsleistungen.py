"""Tests for § 33a EStG Unterhaltsleistungen.

Authority:
- § 33a Abs. 1 EStG (https://www.gesetze-im-internet.de/estg/__33a.html)
- 2025 Grundfreibetrag = €12,096 (§ 32a Abs. 1 EStG).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    TARIFF_2025_GROUND_ALLOWANCE_EUR,
    UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR,
    WageFacts2025,
    compute_joint_ordinary_assessment_2025,
    unterhaltsleistungen_deductible_2025,
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


def _person(slot: str) -> PersonOrdinaryInputs2025:
    return PersonOrdinaryInputs2025(
        slot=slot,
        order_label=slot.replace("_", " ").title(),
        display_name=slot.replace("_", " ").title(),
        owner=slot,
        wage=_wage(slot),
        work_equipment_items=(),
        home_office_days_without_visit=0,
        home_office_days_with_visit=0,
        manual_work_equipment_deduction_eur=Decimal("0.00"),
        telecom_deduction_eur=Decimal("0.00"),
        employment_legal_insurance_deduction_eur=Decimal("0.00"),
        cross_border_tax_help_deduction_eur=Decimal("0.00"),
        health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
    )


class UnterhaltsleistungenLawFunctionTest(unittest.TestCase):
    def test_zero_payments_no_relationship_returns_zero(self) -> None:
        # Loader convention: 0 + empty relationship is the not-declared
        # state and the rule must not fail.
        self.assertEqual(
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("0.00"),
                recipient_income_eur=Decimal("0.00"),
                relationship="",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            ),
            Decimal("0.00"),
        )

    def test_invalid_relationship_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported support_recipient_relationship"):
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("5000.00"),
                recipient_income_eur=Decimal("0.00"),
                relationship="cousin",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            )

    def test_full_deduction_when_recipient_has_no_income(self) -> None:
        # 5000 paid, recipient income 0 → eigenbezuege_reduction = 0 →
        # cap = 12096. min(5000, 12096) = 5000.
        self.assertEqual(
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("5000.00"),
                recipient_income_eur=Decimal("0.00"),
                relationship="parent",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            ),
            Decimal("5000.00"),
        )

    def test_partial_reduction_with_recipient_income(self) -> None:
        # Recipient income 1,624 EUR → 1,624 - 624 = 1,000 reduction.
        # Cap = 12,096 - 1,000 = 11,096. Payments 8,000 < cap → 8,000.
        self.assertEqual(
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("8000.00"),
                recipient_income_eur=Decimal("1624.00"),
                relationship="divorced_spouse",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            ),
            Decimal("8000.00"),
        )

    def test_cap_binding_when_payments_exceed_remaining_grundfreibetrag(self) -> None:
        # Recipient income 5,624 → reduction 5,000 → cap 7,096. Payments
        # 10,000 > cap → deductible 7,096.
        self.assertEqual(
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("10000.00"),
                recipient_income_eur=Decimal("5624.00"),
                relationship="estranged_spouse",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            ),
            Decimal("7096.00"),
        )

    def test_recipient_income_below_eigenbezuege_freibetrag(self) -> None:
        # Income 600 EUR is below the 624 EUR Eigenbezüge Freibetrag → no
        # cap reduction.
        self.assertLess(
            Decimal("600.00"),
            UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR,
        )
        self.assertEqual(
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("5000.00"),
                recipient_income_eur=Decimal("600.00"),
                relationship="parent",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            ),
            Decimal("5000.00"),
        )

    def test_recipient_income_zeros_cap(self) -> None:
        # Recipient income 100,000 → reduction 99,376 → cap clamped to 0.
        self.assertEqual(
            unterhaltsleistungen_deductible_2025(
                support_payments_eur=Decimal("5000.00"),
                recipient_income_eur=Decimal("100000.00"),
                relationship="parent",
                grundfreibetrag_eur=TARIFF_2025_GROUND_ALLOWANCE_EUR,
            ),
            Decimal("0.00"),
        )


class UnterhaltsleistungenStageIntegrationTest(unittest.TestCase):
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
                execution.final_facts["de.ordinary.unterhaltsleistungen"]["deductible_eur"],
                Decimal("0.00"),
            )

    def test_support_payments_reduce_zve(self) -> None:
        # Person 1 (single): wage 60000 → werb 1230 → net 58770.
        # Sonderausgaben 36 → zvE base 58734.
        # Support payments 5000 to a parent with no income → § 33a deduction
        # 5000 → zvE = 58734 - 5000 = 53734.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            support_payments_eur=Decimal("5000.00"),
            support_recipient_income_eur=Decimal("0.00"),
            support_recipient_relationship="parent",
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("53734.00"))


if __name__ == "__main__":
    unittest.main()
