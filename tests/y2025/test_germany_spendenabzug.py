"""Tests for § 10b EStG Spendenabzug.

Authority:
- § 10b Abs. 1 Satz 1 Nr. 1 EStG (https://www.gesetze-im-internet.de/estg/__10b.html)
- § 10b Abs. 1 Sätze 9-10 EStG carryforward (not modeled — fail closed).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    SPENDENABZUG_2025_GDE_FRACTION_CAP,
    WageFacts2025,
    compute_joint_ordinary_assessment_2025,
    spendenabzug_2025,
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


class SpendenabzugLawFunctionTest(unittest.TestCase):
    def test_zero_donations_yields_zero(self) -> None:
        self.assertEqual(
            spendenabzug_2025(
                donations_eur=Decimal("0.00"),
                gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
                carryforward_eur=Decimal("0.00"),
            ),
            Decimal("0.00"),
        )

    def test_donations_under_20pct_cap_fully_deductible(self) -> None:
        # GdE 60,000 → cap = 12,000. Donations 5,000 < cap → 5,000.
        self.assertEqual(
            spendenabzug_2025(
                donations_eur=Decimal("5000.00"),
                gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
                carryforward_eur=Decimal("0.00"),
            ),
            Decimal("5000.00"),
        )

    def test_donations_over_cap_truncate_to_cap(self) -> None:
        # GdE 60,000 → cap = 12,000. Donations 20,000 → truncated to 12,000.
        self.assertEqual(
            spendenabzug_2025(
                donations_eur=Decimal("20000.00"),
                gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
                carryforward_eur=Decimal("0.00"),
            ),
            Decimal("12000.00"),
        )

    def test_carryforward_fails_closed(self) -> None:
        with self.assertRaisesRegex(NotImplementedError, "Großspendenrest"):
            spendenabzug_2025(
                donations_eur=Decimal("5000.00"),
                gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
                carryforward_eur=Decimal("100.00"),
            )

    def test_cap_constant_is_20_pct(self) -> None:
        # Pin the cap constant so the rate cannot drift silently.
        self.assertEqual(SPENDENABZUG_2025_GDE_FRACTION_CAP, Decimal("0.20"))


class SpendenabzugStageIntegrationTest(unittest.TestCase):
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
                execution.final_facts["de.ordinary.spendenabzug"]["deductible_eur"],
                Decimal("0.00"),
            )

    def test_donations_reduce_zve(self) -> None:
        # Single, wage 60000 → werb 1230 → net 58770.
        # Donations 5,000 < 20 % of 58,770 = 11,754. Deductible 5,000.
        # zvE = 58770 - 36 - 5000 = 53734.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            charitable_donations_eur=Decimal("5000.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("53734.00"))

    def test_donations_over_cap_truncate(self) -> None:
        # Donations 20,000 → cap = 0.20 * 58770 = 11,754. Deductible 11,754.
        # zvE = 58770 - 36 - 11754 = 46,980.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            charitable_donations_eur=Decimal("20000.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("46980.00"))

    def test_carryforward_fact_fails_closed(self) -> None:
        # § 10b Abs. 1 Sätze 9-10 carryforwards are not modeled.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            charitable_donations_eur=Decimal("5000.00"),
            charitable_donations_carryforward_eur=Decimal("100.00"),
        )
        with self.assertRaisesRegex(NotImplementedError, "Großspendenrest"):
            compute_joint_ordinary_assessment_2025(inputs)


if __name__ == "__main__":
    unittest.main()
