from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from tax_pipeline.y2025.germany_inputs import load_joint_ordinary_inputs_2025
from tax_pipeline.y2025.germany_law import (
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    compute_joint_ordinary_assessment_2025,
)
from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.paths import YearPaths
from tax_pipeline.run_year import print_headline_summary
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_law import compute_us_assessment_2025

from tax_pipeline.pipelines.y2025.vanilla_checkpoint import (
    compute_germany_vanilla_checkpoint_2025,
    compute_usa_vanilla_checkpoint_2025,
    derive_germany_vanilla_inputs_2025,
)
from tests.generated_demo import GeneratedDemoWorkspace, generate_demo_workspace


class VanillaCheckpointPureTest(unittest.TestCase):
    def _zero_wage(self, owner: str) -> WageFacts2025:
        return WageFacts2025(
            owner=owner,
            source_files=(f"{owner}.pdf",),
            gross_wage_eur=Decimal("10000.00"),
            withheld_wage_tax_eur=Decimal("0.00"),
            withheld_solidarity_surcharge_eur=Decimal("0.00"),
            multiannual_wage_eur=Decimal("0.00"),
            employer_pension_contribution_eur=Decimal("0.00"),
            employee_pension_contribution_eur=Decimal("0.00"),
            employee_health_insurance_eur=Decimal("0.00"),
            employee_nursing_care_insurance_eur=Decimal("0.00"),
            employee_unemployment_insurance_eur=Decimal("0.00"),
        )

    def _person(self, slot: str) -> PersonOrdinaryInputs2025:
        return PersonOrdinaryInputs2025(
            slot=slot,
            order_label=slot,
            display_name=slot,
            owner=slot,
            wage=self._zero_wage(slot),
            work_equipment_items=(),
            home_office_days_without_visit=0,
            home_office_days_with_visit=0,
            manual_work_equipment_deduction_eur=Decimal("0.00"),
            telecom_deduction_eur=Decimal("0.00"),
            employment_legal_insurance_deduction_eur=Decimal("0.00"),
            cross_border_tax_help_deduction_eur=Decimal("0.00"),
            health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
            other_vorsorge_cap_eur=Decimal("1900.00"),
        )

    def test_germany_vanilla_checkpoint_zeroes_section_22nr3_allocations(self) -> None:
        inputs = JointOrdinaryInputs2025(
            people=(self._person("person_1"), self._person("person_2")),
            other_income_22nr3_eur=Decimal("293.48"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            filing_posture="married_joint",
            joint_assessment_prerequisites_validated=True,
            other_income_22nr3_by_person_eur=(Decimal("293.48"), Decimal("0.00")),
        )

        vanilla_inputs = derive_germany_vanilla_inputs_2025(inputs)

        self.assertEqual(vanilla_inputs.other_income_22nr3_eur, Decimal("0.00"))
        self.assertEqual(vanilla_inputs.other_income_22nr3_by_person_eur, ())
        compute_joint_ordinary_assessment_2025(vanilla_inputs)

    def test_germany_vanilla_checkpoint_zeroes_capital_and_discretionary_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            ordinary_inputs = load_joint_ordinary_inputs_2025(paths)

            checkpoint = compute_germany_vanilla_checkpoint_2025(ordinary_inputs)
            assessment = compute_joint_ordinary_assessment_2025(checkpoint.assessment_inputs)

            self.assertEqual(checkpoint.taxable_income_eur, assessment.joint_taxable_income_eur)
            self.assertEqual(checkpoint.income_tax_eur, assessment.joint_income_tax_eur)
            self.assertEqual(checkpoint.soli_eur, assessment.joint_solidarity_surcharge_eur)
            self.assertEqual(checkpoint.total_tax_eur, assessment.joint_income_tax_eur + assessment.joint_solidarity_surcharge_eur)
            self.assertEqual(checkpoint.refund_or_balance_due_eur, assessment.ordinary_refund_before_capital_eur)

            self.assertEqual(checkpoint.assessment_inputs.other_income_22nr3_eur, Decimal("0.00"))
            self.assertEqual(checkpoint.assessment_inputs.prepayments_eur, ordinary_inputs.prepayments_eur)
            for person in checkpoint.assessment_inputs.people:
                self.assertEqual(person.home_office_days_without_visit, 0)
                self.assertEqual(person.home_office_days_with_visit, 0)
                self.assertEqual(person.telecom_deduction_eur, Decimal("0.00"))
                self.assertEqual(person.employment_legal_insurance_deduction_eur, Decimal("0.00"))
                self.assertEqual(person.cross_border_tax_help_deduction_eur, Decimal("0.00"))
                self.assertEqual(person.work_equipment_items, ())

    def test_usa_vanilla_checkpoint_keeps_only_wages_standard_deduction_and_payment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            full_inputs = load_us_assessment_inputs_2025(paths)

            checkpoint = compute_usa_vanilla_checkpoint_2025(full_inputs)
            assessment = compute_us_assessment_2025(checkpoint.assessment_inputs)

            self.assertEqual(checkpoint.adjusted_gross_income_usd, assessment.regular_tax.adjusted_gross_income_usd)
            self.assertEqual(checkpoint.taxable_income_usd, assessment.regular_tax.taxable_income_usd)
            self.assertEqual(checkpoint.regular_tax_usd, assessment.regular_tax.regular_tax_before_credits_usd)
            self.assertEqual(checkpoint.total_tax_usd, assessment.total_tax_usd)
            self.assertEqual(checkpoint.refund_or_balance_due_usd, assessment.refund_if_positive_else_balance_due_usd)

            facts = checkpoint.assessment_inputs.capital_facts
            self.assertEqual(facts.ordinary_dividends_usd, Decimal("0.00"))
            self.assertEqual(facts.qualified_dividends_usd, Decimal("0.00"))
            self.assertEqual(facts.capital_gain_distributions_usd, Decimal("0.00"))
            self.assertEqual(facts.interest_income_usd, Decimal("0.00"))
            self.assertEqual(facts.substitute_payments_usd, Decimal("0.00"))
            self.assertEqual(facts.staking_income_usd, Decimal("0.00"))
            self.assertEqual(facts.foreign_tax_paid_usd, Decimal("0.00"))
            self.assertEqual(checkpoint.assessment_inputs.treaty_inputs.use_treaty_resourcing, False)

    def test_usa_vanilla_checkpoint_disables_niit_and_ftc_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            full_inputs = load_us_assessment_inputs_2025(paths)

            checkpoint = compute_usa_vanilla_checkpoint_2025(full_inputs)
            assessment = compute_us_assessment_2025(checkpoint.assessment_inputs)

            self.assertEqual(assessment.niit.niit_usd, Decimal("0.00"))
            self.assertEqual(assessment.ftc.total_allowed_ftc_usd, Decimal("0.00"))
            self.assertEqual(assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd, Decimal("0.00"))


class VanillaCheckpointOutputShapeTest(unittest.TestCase):
    demo: GeneratedDemoWorkspace

    @classmethod
    def setUpClass(cls) -> None:
        cls.demo = generate_demo_workspace()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.demo.cleanup()

    def test_germany_model_results_include_vanilla_checkpoint_block(self) -> None:
        results = json.loads((self.demo.paths.analysis_root / "germany-model-results.json").read_text())
        checkpoint = results["vanilla_checkpoint"]
        self.assertEqual(
            set(checkpoint),
            {
                "taxable_income_eur",
                "income_tax_eur",
                "soli_eur",
                "total_tax_eur",
                "refund_or_balance_due_eur",
            },
        )

    def test_usa_model_results_include_vanilla_checkpoint_block(self) -> None:
        results = json.loads((self.demo.paths.analysis_root / "us-tax-estimate.json").read_text())
        checkpoint = results["vanilla_checkpoint"]
        self.assertEqual(
            set(checkpoint),
            {
                "adjusted_gross_income_usd",
                "taxable_income_usd",
                "regular_tax_usd",
                "total_tax_usd",
                "refund_or_balance_due_usd",
            },
        )

    def test_germany_summary_includes_vanilla_checkpoint_section(self) -> None:
        summary = (self.demo.paths.analysis_root / "germany-summary.md").read_text()
        self.assertIn("## Vanilla checkpoint for commercial software comparison", summary)

    def test_usa_summary_includes_vanilla_checkpoint_section(self) -> None:
        summary = (self.demo.paths.analysis_root / "us-tax-estimate.md").read_text()
        self.assertIn("## Vanilla checkpoint for commercial software comparison", summary)


class VanillaCheckpointHeadlineTest(unittest.TestCase):
    def test_print_headline_summary_includes_vanilla_checkpoint_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()
            (paths.analysis_root / "final-legal-output.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "tax_year": 2025,
                        "source_role": "test final legal output consumed by print_headline_summary",
                        "germany": {
                            "forms": {
                                "profile": {
                                    "jurisdictions": {
                                        "germany": {"enabled": True},
                                        "usa": {"enabled": True},
                                    }
                                },
                                "results": {
                                    "refunds": {"final_target_refund_eur": "3725.72"},
                                    "vanilla_checkpoint": {"refund_or_balance_due_eur": "1200.00"},
                                },
                            }
                        },
                        "usa": {
                            "forms": {
                                "tax_estimate": {
                                    "payments": {
                                        "refund_if_positive_else_balance_due_usd": "428.64",
                                        "refund_if_positive_else_balance_due_with_treaty_resourcing_usd": "1126.53",
                                    },
                                    "vanilla_checkpoint": {"refund_or_balance_due_usd": "314.15"},
                                }
                            }
                        },
                    }
                )
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print_headline_summary(paths)

            self.assertIn("  Germany vanilla checkpoint refund: 1200.00 EUR", buffer.getvalue())
            self.assertIn("  U.S. vanilla checkpoint refund: 314.15 USD", buffer.getvalue())
