"""DE25-EUER end-to-end — § 18 / § 4 Abs. 3 EStG self-employment income.

Authority:
- § 18 EStG — https://www.gesetze-im-internet.de/estg/__18.html
- § 4 Abs. 3 EStG — https://www.gesetze-im-internet.de/estg/__4.html
- § 2 Abs. 3 EStG (Verlustausgleich) — https://www.gesetze-im-internet.de/estg/__2.html
- § 15 EStG (out of scope) — https://www.gesetze-im-internet.de/estg/__15.html

Exercises the full ordinary rule graph: business receipts/expenses →
DE25-EUER (§ 4 Abs. 3 EÜR profit) → DE25-07 taxable income → § 32a tariff,
plus the loader fail-closed contracts. Asserts concrete euro outcomes,
hand-derivable from the cited law (CLAUDE.md).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.y2025.germany_inputs import load_joint_ordinary_inputs_2025
from tax_pipeline.y2025.germany_law import (
    BusinessIncomeInputs2025,
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    compute_joint_ordinary_assessment_2025,
)

D = Decimal


def _wage(owner: str, gross: str = "60000.00") -> WageFacts2025:
    return WageFacts2025(
        owner=owner,
        source_files=("synthetic.pdf",),
        gross_wage_eur=D(gross),
        withheld_wage_tax_eur=D("0.00"),
        withheld_solidarity_surcharge_eur=D("0.00"),
        multiannual_wage_eur=D("0.00"),
        employer_pension_contribution_eur=D("0.00"),
        employee_pension_contribution_eur=D("0.00"),
        employee_health_insurance_eur=D("0.00"),
        employee_nursing_care_insurance_eur=D("0.00"),
        employee_unemployment_insurance_eur=D("0.00"),
    )


def _person(slot: str, gross: str = "60000.00") -> PersonOrdinaryInputs2025:
    return PersonOrdinaryInputs2025(
        slot=slot,
        order_label=slot.replace("_", " ").title(),
        display_name=slot.replace("_", " ").title(),
        owner=slot,
        wage=_wage(slot, gross),
        work_equipment_items=(),
        home_office_days_without_visit=0,
        home_office_days_with_visit=0,
        manual_work_equipment_deduction_eur=D("0.00"),
        telecom_deduction_eur=D("0.00"),
        employment_legal_insurance_deduction_eur=D("0.00"),
        cross_border_tax_help_deduction_eur=D("0.00"),
        health_insurance_sick_pay_reduction_rate=D("0.04"),
    )


def _single_inputs(business: BusinessIncomeInputs2025 | None, gross: str = "60000.00"):
    return JointOrdinaryInputs2025(
        people=(_person("person_1", gross),),
        other_income_22nr3_eur=D("0.00"),
        other_income_22nr3_threshold_eur=D("256.00"),
        prepayments_eur=D("0.00"),
        business_income=business,
    )


class Euer18ProfitFlowsIntoTaxableIncomeTest(unittest.TestCase):
    def test_profit_adds_to_zve_on_top_of_wages(self) -> None:
        # Single, wage 60,000 → § 9a Arbeitnehmer-Pauschbetrag 1,230 →
        # net employment 58,770 (§ 9a applies to wages ONLY, not § 18).
        # § 4 Abs. 3 profit = 80,000 − 18,250 = 61,750.
        # Sonderausgaben-Pauschbetrag 36.
        # zvE = 58,770 + 61,750 − 36 = 120,484.
        assessment = compute_joint_ordinary_assessment_2025(
            _single_inputs(
                BusinessIncomeInputs2025(
                    operating_receipts_eur=D("80000.00"),
                    operating_expenses_eur=D("18250.00"),
                )
            )
        )
        self.assertEqual(assessment.joint_taxable_income_eur, D("120484.00"))

    def test_arbeitnehmer_pauschbetrag_is_not_applied_to_business_income(self) -> None:
        # § 9a is wage-only: with zero wages, no 1,230 allowance touches the
        # § 18 profit. Profit 61,750; zvE = 61,750 − 36 = 61,714 (NOT
        # 61,750 − 1,230 − 36).
        assessment = compute_joint_ordinary_assessment_2025(
            _single_inputs(
                BusinessIncomeInputs2025(
                    operating_receipts_eur=D("80000.00"),
                    operating_expenses_eur=D("18250.00"),
                ),
                gross="0.00",
            )
        )
        self.assertEqual(assessment.joint_taxable_income_eur, D("61714.00"))

    def test_verlust_reduces_zve_and_is_not_floored(self) -> None:
        # § 2 Abs. 3 Verlustausgleich: a § 4 Abs. 3 loss reduces the income
        # sum. Receipts 10,000, expenses 14,500 → −4,500.
        # zvE = 58,770 − 4,500 − 36 = 54,234.
        assessment = compute_joint_ordinary_assessment_2025(
            _single_inputs(
                BusinessIncomeInputs2025(
                    operating_receipts_eur=D("10000.00"),
                    operating_expenses_eur=D("14500.00"),
                )
            )
        )
        self.assertEqual(assessment.joint_taxable_income_eur, D("54234.00"))

    def test_no_business_income_matches_wage_only_baseline(self) -> None:
        # business_income=None → zero § 18 profit → zvE = 58,770 − 36 = 58,734.
        assessment = compute_joint_ordinary_assessment_2025(_single_inputs(None))
        self.assertEqual(assessment.joint_taxable_income_eur, D("58734.00"))


class EuerLoaderFailClosedTest(unittest.TestCase):
    """Loader contracts (CLAUDE.md fail-closed posture)."""

    def _demo_with_elections(self, tmp: str, **elections):
        paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
        profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
        profile.setdefault("elections", {}).update(elections)
        paths.profile_path.write_text(json.dumps(profile), encoding="utf-8")
        return paths

    def test_employee_default_has_no_business_income(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            inputs = load_joint_ordinary_inputs_2025(paths)
            self.assertIsNone(inputs.business_income)

    def test_self_employed_freiberuflich_loads_business_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp, worker_type="self_employed", de_self_employment_class="freiberuflich_18"
            )
            (paths.config_root / "business-income.csv").write_text(
                "key,amount_eur,source,note\n"
                "operating_receipts_eur,80000.00,test,\n"
                "operating_expenses_eur,18250.00,test,\n",
                encoding="utf-8",
            )
            inputs = load_joint_ordinary_inputs_2025(paths)
            self.assertIsNotNone(inputs.business_income)
            self.assertEqual(inputs.business_income.operating_receipts_eur, D("80000.00"))
            self.assertEqual(inputs.business_income.operating_expenses_eur, D("18250.00"))
            self.assertEqual(inputs.business_income.self_employment_class, "freiberuflich_18")

    def test_self_employed_without_facts_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp, worker_type="self_employed", de_self_employment_class="freiberuflich_18"
            )
            with self.assertRaisesRegex(ValueError, "business-income"):
                load_joint_ordinary_inputs_2025(paths)

    def test_gewerbe_15_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp, worker_type="self_employed", de_self_employment_class="gewerbe_15"
            )
            with self.assertRaisesRegex(ValueError, r"§ 15 EStG|gewerbe_15"):
                load_joint_ordinary_inputs_2025(paths)


if __name__ == "__main__":
    unittest.main()
