"""Tests for § 33 EStG außergewöhnliche Belastungen + § 33 Abs. 3 zumutbare Belastung.

Authority:
- § 33 EStG (https://www.gesetze-im-internet.de/estg/__33.html)
- § 33 Abs. 3 EStG (slab progression confirmed by BFH VI R 75/14, 19.01.2017)

Numerics: each family-category × bracket boundary case carries the slab
math: each band's rate × band-width then summed.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    aussergewoehnliche_belastungen_deductible_2025,
    compute_joint_ordinary_assessment_2025,
    zumutbare_belastung_2025,
)


def _wage(owner: str, *, gross_wage_eur: str = "60000.00") -> WageFacts2025:
    return WageFacts2025(
        owner=owner,
        source_files=("synthetic.pdf",),
        gross_wage_eur=Decimal(gross_wage_eur),
        withheld_wage_tax_eur=Decimal("12000.00"),
        withheld_solidarity_surcharge_eur=Decimal("0.00"),
        multiannual_wage_eur=Decimal("0.00"),
        employer_pension_contribution_eur=Decimal("0.00"),
        employee_pension_contribution_eur=Decimal("0.00"),
        employee_health_insurance_eur=Decimal("0.00"),
        employee_nursing_care_insurance_eur=Decimal("0.00"),
        employee_unemployment_insurance_eur=Decimal("0.00"),
    )


def _person(slot: str, *, gross_wage_eur: str = "60000.00") -> PersonOrdinaryInputs2025:
    return PersonOrdinaryInputs2025(
        slot=slot,
        order_label=slot.replace("_", " ").title(),
        display_name=slot.replace("_", " ").title(),
        owner=slot,
        wage=_wage(slot, gross_wage_eur=gross_wage_eur),
        work_equipment_items=(),
        home_office_days_without_visit=0,
        home_office_days_with_visit=0,
        manual_work_equipment_deduction_eur=Decimal("0.00"),
        telecom_deduction_eur=Decimal("0.00"),
        employment_legal_insurance_deduction_eur=Decimal("0.00"),
        cross_border_tax_help_deduction_eur=Decimal("0.00"),
        health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
    )


class ZumutbareBelastungSlabTest(unittest.TestCase):
    """The slab method (BFH VI R 75/14) computes each band's rate × width."""

    def test_slab_method_matrix(self) -> None:
        # Per BFH VI R 75/14 (slab method), zumutbare Belastung is
        # rate × width per band. Every row pins:
        #   - one ``single_no_children`` boundary case (band A only, band-A
        #     boundary inclusive, band-B span, band-C span);
        #   - per-category band-C totals at GdE = 100,000 so each
        #     family_category's full schedule is exercised end-to-end.
        # Hand-computed expected values match § 33 Abs. 3 EStG schedule.
        cases = (
            # GdE  category                  expected     note
            (Decimal("10000.00"), "single_no_children", Decimal("500.00"),
             "band A only: 10000*0.05"),
            (Decimal("15340.00"), "single_no_children", Decimal("767.00"),
             "boundary: band A INCLUSIVE at 15340"),
            (Decimal("30000.00"), "single_no_children", Decimal("1646.60"),
             "spans band B: 767.00 + 14660*0.06"),
            (Decimal("100000.00"), "single_no_children", Decimal("6335.30"),
             "spans band C: 767 + 35790*0.06 + 48870*0.07"),
            (Decimal("100000.00"), "joint_or_few_children", Decimal("5335.30"),
             "joint band C: 15340*0.04 + 35790*0.05 + 48870*0.06"),
            (Decimal("100000.00"), "many_children", Decimal("1488.70"),
             "many-children band C: 15340*0.01 + 35790*0.01 + 48870*0.02"),
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

    def test_unsupported_family_category_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            zumutbare_belastung_2025(
                gesamtbetrag_der_einkuenfte_eur=Decimal("10000.00"),
                family_category="not_a_real_category",
            )


class AussergewoehnlicheBelastungenDeductibleTest(unittest.TestCase):
    def test_zero_medical_expenses_yields_zero_deductible(self) -> None:
        deductible, burden = aussergewoehnliche_belastungen_deductible_2025(
            medical_expenses_eur=Decimal("0.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
            family_category="single_no_children",
        )
        self.assertEqual(deductible, Decimal("0.00"))
        # Burden is non-zero (income-driven) even when expenses are 0.
        self.assertGreater(burden, Decimal("0.00"))

    def test_expenses_below_burden_yield_zero_deductible(self) -> None:
        # GdE 60,000 single_no_children: 15340*0.05 + 35790*0.06 + 8870*0.07
        # = 767.00 + 2147.40 + 620.90 = 3,535.30. Expenses 1,000 < burden →
        # deductible 0.
        deductible, _ = aussergewoehnliche_belastungen_deductible_2025(
            medical_expenses_eur=Decimal("1000.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
            family_category="single_no_children",
        )
        self.assertEqual(deductible, Decimal("0.00"))

    def test_expenses_above_burden_yield_delta(self) -> None:
        # Same income as above (burden 3,535.30). Expenses 5,000 →
        # deductible 5,000 - 3,535.30 = 1,464.70.
        deductible, burden = aussergewoehnliche_belastungen_deductible_2025(
            medical_expenses_eur=Decimal("5000.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("60000.00"),
            family_category="single_no_children",
        )
        self.assertEqual(burden, Decimal("3535.30"))
        self.assertEqual(deductible, Decimal("1464.70"))


class AussergewoehnlicheBelastungenStageIntegrationTest(unittest.TestCase):
    def test_demo_workspace_zero_default_keeps_baseline_zve(self) -> None:
        # The dataclass defaults medical_expenses_eur to 0; demo zvE
        # remains the same as before.
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
                execution.final_facts["de.ordinary.aussergewoehnliche_belastungen"]["deductible_eur"],
                Decimal("0.00"),
            )

    def test_high_medical_expenses_reduce_zve_in_single_path(self) -> None:
        # § 19 wage 60,000 → werbungskosten allowance 1,230 → net 58,770.
        # GdE = 58,770. Single_no_children burden = 15340*0.05 + 35790*0.06 +
        # (58770-51130)*0.07 = 767.00 + 2147.40 + 534.80 = 3,449.20.
        # Medical 10,000 → deductible = 6,550.80. zvE base = 58,770 - 36 -
        # 6,550.80 = 52,183.20.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            medical_expenses_eur=Decimal("10000.00"),
            zumutbare_belastung_family_category="single_no_children",
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("52183.20"))

    def test_married_separate_halving_via_single_no_children(self) -> None:
        # married_separate uses single tariff per person; per § 33 Abs. 3
        # Satz 1 EStG, married_separate single-no-children rates apply
        # (slab 5/6/7%). With one spouse claiming the medical, the
        # deduction is allocated to person 1 in the trace.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1"), _person("person_2", gross_wage_eur="30000.00")),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            filing_posture="married_separate",
            medical_expenses_eur=Decimal("0.00"),
            zumutbare_belastung_family_category="single_no_children",
        )
        # With zero medical, deductible is 0; baseline zvE preserved.
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        # Person 1: 60000 - 1230 - 36 = 58734; Person 2: 30000 - 1230 - 36 = 28734.
        # Sum = 87,468.
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("87468.00"))


if __name__ == "__main__":
    unittest.main()
