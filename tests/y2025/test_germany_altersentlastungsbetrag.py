"""Tests for § 24a EStG Altersentlastungsbetrag (DE25-ALTERSENTLASTUNGSBETRAG).

Authority:
- § 24a EStG (https://www.gesetze-im-internet.de/estg/__24a.html) sets the
  cohort-keyed sliding allowance and the 64-year age threshold.
- § 24a Satz 5 EStG and the Anlage to § 24a EStG fix the rate / cap row by
  the calendar year the taxpayer first met the age threshold.
- § 2 Abs. 4 EStG places the allowance between the Gesamtbetrag der
  Einkünfte and the Sonderausgabenabzug.

The numeric assertions below cite the official Anlage entries by year.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    ALTERSENTLASTUNGSBETRAG_2025_TABLE,
    ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS,
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    altersentlastungsbetrag_2025,
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


def _person(slot: str, *, birth_year: int = 0) -> PersonOrdinaryInputs2025:
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
        birth_year=birth_year,
    )


class Altersentlastungsbetrag2025Test(unittest.TestCase):
    """Direct law-function tests against § 24a EStG cohort table."""

    def test_below_age_threshold_returns_zero(self) -> None:
        # § 24a Satz 3 EStG: a taxpayer who only turned 64 *during* 2025
        # does not yet qualify in 2025. Birth year 1961 + 64 = 2025 means
        # the 64-year threshold is reached *during* 2025, not before.
        self.assertEqual(
            altersentlastungsbetrag_2025(
                birth_year=1961,
                eligible_income_eur=Decimal("5000.00"),
                tax_year=2025,
            ),
            Decimal("0.00"),
        )

    def test_birth_year_zero_means_not_declared_yields_zero(self) -> None:
        # Loader convention: 0 is the "not declared" sentinel; per § 24a
        # EStG no allowance is granted without the cohort fact.
        self.assertEqual(
            altersentlastungsbetrag_2025(
                birth_year=0,
                eligible_income_eur=Decimal("100000.00"),
                tax_year=2025,
            ),
            Decimal("0.00"),
        )

    def test_birth_1960_uses_2024_cohort_rate_and_cap(self) -> None:
        # Birth year 1960 → year_turned_64 = 2024 → table row (0.136, 646).
        # Source: § 24a Satz 5 EStG Anlage 2024 cohort row.
        # 5000 * 0.136 = 680 → capped at 646.
        rate, cap = ALTERSENTLASTUNGSBETRAG_2025_TABLE[2024]
        self.assertEqual(rate, Decimal("0.136"))
        self.assertEqual(cap, Decimal("646"))
        self.assertEqual(
            altersentlastungsbetrag_2025(
                birth_year=1960,
                eligible_income_eur=Decimal("5000.00"),
                tax_year=2025,
            ),
            Decimal("646.00"),
        )

    def test_birth_1960_below_cap_returns_rate_times_base(self) -> None:
        # 4000 * 0.136 = 544 EUR, below the 646 cap.
        self.assertEqual(
            altersentlastungsbetrag_2025(
                birth_year=1960,
                eligible_income_eur=Decimal("4000.00"),
                tax_year=2025,
            ),
            Decimal("544.00"),
        )

    def test_birth_pre_2005_uses_2005_row(self) -> None:
        # Per § 24a Satz 5 EStG, taxpayers who first met the threshold
        # before 2005 use the 2005 row (40 % / €1,900). Birth year 1940
        # turned 64 in 2004, before the 2005 schedule starts; the
        # implementation clamps to 2005.
        self.assertEqual(
            altersentlastungsbetrag_2025(
                birth_year=1940,
                eligible_income_eur=Decimal("3000.00"),
                tax_year=2025,
            ),
            Decimal("1200.00"),  # 3000 * 0.40
        )
        self.assertEqual(
            altersentlastungsbetrag_2025(
                birth_year=1940,
                eligible_income_eur=Decimal("10000.00"),
                tax_year=2025,
            ),
            Decimal("1900.00"),  # capped
        )

    def test_age_threshold_constant_is_64(self) -> None:
        # Pin the statutory threshold so a typo in the constant cannot
        # silently change the cohort qualification.
        self.assertEqual(ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS, 64)

    def test_table_covers_2005_to_2025(self) -> None:
        # § 24a EStG Anlage carries cohorts 2005-2058; 2025 is the
        # most-recently-relevant assessment year for this implementation.
        self.assertIn(2005, ALTERSENTLASTUNGSBETRAG_2025_TABLE)
        self.assertIn(2024, ALTERSENTLASTUNGSBETRAG_2025_TABLE)
        self.assertIn(2025, ALTERSENTLASTUNGSBETRAG_2025_TABLE)


class AltersentlastungsbetragStageIntegrationTest(unittest.TestCase):
    """End-to-end integration through ``compute_joint_ordinary_assessment_2025``.

    The eligible base for the rule is § 22 Nr. 3 income (other_income_22nr3
    after Freigrenze). § 19 wages are excluded by § 24a Satz 2 Nr. 1 EStG.
    """

    def test_no_qualifying_taxpayer_yields_zero_household_total(self) -> None:
        # Single 35-year-old: birth_year 1990 → year_turned_64 = 2054 →
        # not yet qualified in 2025. zvE unchanged.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1", birth_year=1990),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        # zvE math unchanged from the pre-§-24a baseline:
        # gross 60000 - werbungskosten 1230 - sonderausgaben 36 = 58734
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("58734.00"))

    def test_qualifying_taxpayer_with_no_other_income_yields_zero_allowance(self) -> None:
        # Birth 1955 → year_turned_64 = 2019 → qualifies. But with no
        # § 22 Nr. 3 income the eligible base is 0, so the allowance is 0.
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1", birth_year=1955),),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("58734.00"))

    def test_qualifying_taxpayer_with_other_income_reduces_zve(self) -> None:
        # Birth 1955, year_turned_64 = 2019 → table row (0.176, 836).
        # § 22 Nr. 3 income = 1000 EUR > Freigrenze 256 EUR, so eligible
        # base = 1000 EUR. Allowance = min(836, 1000 * 0.176) = 176 EUR.
        rate, cap = ALTERSENTLASTUNGSBETRAG_2025_TABLE[2019]
        self.assertEqual(rate, Decimal("0.176"))
        self.assertEqual(cap, Decimal("836"))
        inputs = JointOrdinaryInputs2025(
            people=(_person("person_1", birth_year=1955),),
            other_income_22nr3_eur=Decimal("1000.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        # Baseline (no allowance) zvE would be 58734 + 1000 = 59734;
        # with the §-24a allowance: 59734 - 176 = 59558.
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("59558.00"))

    def test_married_joint_each_spouse_carries_own_cohort(self) -> None:
        # Spouse 1 born 1955 (qualifies, rate 0.176 / cap 836);
        # Spouse 2 born 1985 (does not qualify in 2025).
        # § 22 Nr. 3 income aggregate = 2000 EUR allocated 1500 + 500.
        # 1500 > 256 (taxable for spouse 1) → § 24a base = 1500 →
        # min(836, 1500 * 0.176) = min(836, 264.00) = 264.00.
        # 500 > 256 (taxable for spouse 2) → spouse 2 not yet 64 → 0.
        # Household allowance = 264.
        inputs = JointOrdinaryInputs2025(
            people=(
                _person("person_1", birth_year=1955),
                _person("person_2", birth_year=1985),
            ),
            other_income_22nr3_eur=Decimal("2000.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            other_income_22nr3_by_person_eur=(Decimal("1500.00"), Decimal("500.00")),
            prepayments_eur=Decimal("0.00"),
            filing_posture="married_joint",
            joint_assessment_prerequisites_validated=True,
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        # Per-person § 24a allowances and the resulting household
        # taxable-income reduction are exposed via the rule's executed
        # final_facts, not the typed assessment view dataclass; verify the
        # household-level zvE picks up the −264.00 reduction. The other
        # ordinary math remains identical to test_qualifying_taxpayer_*.
        # Joint baseline:
        #   sum(net_emp) = 2 * 58770 = 117540 (60000 - 1230 each, summed)
        #   + other_income_22nr3 = 2000 → 119540
        #   − pauschbetrag_joint (72) → 119468
        #   − §24a (264) → 119204
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("119204.00"))

    def test_demo_workspace_has_no_qualifying_taxpayer_so_zero_total(self) -> None:
        # The demo workspace does not declare a birth_year, so birth_year
        # defaults to 0 (the "not declared" sentinel) for every person and
        # the household total is 0 EUR. This protects the demo's existing
        # zvE numerics.
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
                execution.final_facts["de.ordinary.altersentlastungsbetrag"]["total_eur"],
                Decimal("0.00"),
            )


if __name__ == "__main__":
    unittest.main()
