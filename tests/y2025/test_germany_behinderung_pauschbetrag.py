"""Tests for § 33b EStG Behinderten-Pauschbetrag.

Authority:
- § 33b Abs. 3 EStG (https://www.gesetze-im-internet.de/estg/__33b.html)
- Behinderten-Pauschbetragsgesetz BGBl. I 2020 S. 2770 — doubled the
  rates effective 2021; the 2025 statute carries those rates.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR,
    BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR,
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    behinderung_pauschbetrag_2025,
    compute_joint_ordinary_assessment_2025,
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


def _person(slot: str, *, gdb: int = 0, hilflos_or_blind: bool = False, gross_wage_eur: str = "60000.00") -> PersonOrdinaryInputs2025:
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
        gdb=gdb,
        hilflos_or_blind=hilflos_or_blind,
    )


class BehinderungPauschbetragLawFunctionTest(unittest.TestCase):
    def test_full_schedule_table_and_hilflos_blind_override(self) -> None:
        # Pin every official § 33b Abs. 3 tier (decadic GdB 20-100) so a
        # typo in the constant table cannot silently change a
        # Pauschbetrag, plus the § 33b Abs. 3 Satz 3 hilflos/blind
        # erhöhter Pauschbetrag (€7,400 — supersedes the GdB schedule).
        expected_schedule = {
            0: Decimal("0.00"),
            20: Decimal("384.00"),
            30: Decimal("620.00"),
            40: Decimal("860.00"),
            50: Decimal("1140.00"),
            60: Decimal("1440.00"),
            70: Decimal("1780.00"),
            80: Decimal("2120.00"),
            90: Decimal("2460.00"),
            100: Decimal("2840.00"),
        }
        for gdb, amount in expected_schedule.items():
            with self.subTest(gdb=gdb, hilflos_or_blind=False):
                if gdb > 0:
                    self.assertEqual(
                        BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[gdb], amount
                    )
                self.assertEqual(
                    behinderung_pauschbetrag_2025(
                        gdb=gdb, hilflos_or_blind=False
                    ),
                    amount,
                )

        # § 33b Abs. 3 Satz 3 erhöhter Pauschbetrag — overrides schedule.
        self.assertEqual(
            BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR,
            Decimal("7400.00"),
        )
        for gdb in (0, 80):  # at low and high GdB, hilflos overrides.
            with self.subTest(gdb=gdb, hilflos_or_blind=True):
                self.assertEqual(
                    behinderung_pauschbetrag_2025(gdb=gdb, hilflos_or_blind=True),
                    Decimal("7400.00"),
                )

    def test_invalid_gdb_fails_closed(self) -> None:
        # GdB must be a multiple of 10 in [20, 100].
        for invalid_gdb in (10, 25, 110):
            with self.subTest(gdb=invalid_gdb):
                with self.assertRaisesRegex(
                    ValueError, "Unsupported Grad der Behinderung"
                ):
                    behinderung_pauschbetrag_2025(
                        gdb=invalid_gdb, hilflos_or_blind=False
                    )


class BehinderungPauschbetragStageIntegrationTest(unittest.TestCase):
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
                execution.final_facts["de.ordinary.behinderung_pauschbetrag"]["total_eur"],
                Decimal("0.00"),
            )

    def test_single_gdb_50_reduces_zve(self) -> None:
        # Single, GdB 50 (1,140 EUR allowance). Baseline zvE = 58734;
        # post-§-33b: 58734 - 1140 = 57594.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1", gdb=50),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("57594.00"))

    def test_married_joint_both_disabled_sums_per_person(self) -> None:
        # Both spouses GdB 100 (2,840 EUR each). Joint allowance = 5,680.
        # Baseline joint zvE: 2 * (60000 - 1230) = 117540 - 72 = 117468.
        # Post-§-33b: 117468 - 5680 = 111788.
        inputs = JointOrdinaryInputs2025(
            people=(
                _person("person_1", gdb=100),
                _person("person_2", gdb=100),
            ),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            filing_posture="married_joint",
            joint_assessment_prerequisites_validated=True,
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("111788.00"))

    def test_hilflos_path_supersedes_gdb_schedule(self) -> None:
        # Single, hilflos → 7,400 EUR allowance. Baseline 58734 → 51334.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1", gdb=80, hilflos_or_blind=True),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("51334.00"))


if __name__ == "__main__":
    unittest.main()
