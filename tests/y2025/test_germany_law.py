from __future__ import annotations

import tempfile
import unittest
import csv
import io
from decimal import Decimal
from pathlib import Path
import sys
import json
import os
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GERMANY_LAW_SPEC_ROOT = PROJECT_ROOT / "tax_pipeline" / "law_spec" / "germany" / "2025"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.y2025.germany_inputs import load_joint_ordinary_inputs_2025
from tax_pipeline.y2025.germany_law import (
    GermanyCapitalAssessmentInputs2025,
    GermanyBankCapitalCertificate2025,
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
    GermanyTreatyDividendItem2025,
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR,
    RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025,
    RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR,
    WageFacts2025,
    capital_tax_after_foreign_tax_credit_2025,
    compute_germany_capital_assessment_2025 as _compute_germany_capital_assessment_2025,
    compute_joint_ordinary_assessment_2025,
    deductible_basic_health_contribution_2025,
    foreign_tax_credit_32d5_cap_2025,
    german_income_tax_split_2025,
    german_income_tax_single_2025,
    german_soli_assessment_2025,
    home_office_tagespauschale_2025,
    other_income_22nr3_taxable_2025,
    other_vorsorge_allowed_employee_2025,
    retirement_special_expense_deduction_2025,
    saver_allowance_for_spouse_20_9_2025,
    treaty_relieved_capital_tax_2025,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025 import (
    germany_elster_entry_sheet,
    germany_model,
    germany_projections as _germany_projections,
)
from tests._germany_derived_facts import (
    germany_children_derived_facts_for_empty_household,
    germany_derived_facts_for_inputs,
)


def compute_germany_capital_assessment_2025(
    inputs: GermanyCapitalAssessmentInputs2025,
    *,
    derived_facts=None,
):
    """Test-suite wrapper: pre-compute derived facts, then call the real function.

    F-A4 (architecture review, ``.review/2026-05-01-final/architecture.md``)
    removed the in-memory Pipeline 1 fallback that the real
    ``compute_germany_capital_assessment_2025`` used to fall back on when
    ``derived-facts.json`` was not on disk. Tests that bypass ``run_year``
    must now materialize the boundary state explicitly. This wrapper
    runs the canonical ``germany_derivation_law_rules_2025`` derivation
    pipeline in-memory (via ``tests/_germany_derived_facts.py``) and
    forwards the resulting ``de.derived.*`` mapping to the real function
    through its ``derived_facts`` keyword argument — keeping the test
    surface unchanged while enforcing the production fail-closed
    contract.

    Tests that drive ``germany_model.compute_capital_buckets`` (which
    constructs ``GermanyCapitalAssessmentInputs2025`` internally from
    mocked ``SALES_CSV`` / ``INCOME_CSV`` and forwards through to
    ``compute_germany_capital_assessment_2025``) get the same boundary
    treatment because this wrapper is patched into the
    ``germany_model`` module namespace below — every call from
    ``compute_capital_buckets`` lands here first.

    Authority: § 32d Abs. 5 EStG per-Posten audit trail
    (https://www.gesetze-im-internet.de/estg/__32d.html); the boundary
    state must travel through ``derived_facts`` (or
    ``derived-facts.json`` on disk) so Pipeline 1 staleness cannot hide
    behind Pipeline 2 results.
    """
    if derived_facts is None:
        derived_facts = germany_derived_facts_for_inputs(inputs)
    return _compute_germany_capital_assessment_2025(
        inputs, derived_facts=derived_facts
    )


# Patch the symbol ``germany_model`` imported at module load. Tests that
# call ``germany_model.compute_capital_buckets`` (which forwards through
# to ``compute_germany_capital_assessment_2025``) need the wrapper to
# materialize ``de.derived.*`` from in-memory inputs because those tests
# bypass ``run_year`` and don't have ``derived-facts.json`` on disk.
# Production callers (``germany_model.main()``) only see this patch
# during the test process and still resolve the on-disk artifact when
# the workspace contains one (the wrapper short-circuits when
# ``derived_facts`` is supplied explicitly).
germany_model.compute_germany_capital_assessment_2025 = (
    compute_germany_capital_assessment_2025
)


def compute_germany_children_assessment_2025(
    *,
    ordinary_taxable_income_eur,
    ordinary_income_tax_eur,
    filing_posture: str,
    derived_facts=None,
):
    """Test-suite wrapper: inject in-memory derived facts for the children sub-graph.

    Mirrors the capital wrapper above (F-A4 architecture review): tests
    that call ``germany_model.main()`` without ``derived-facts.json`` on
    disk receive an in-memory ``de.derived.children_*`` mapping
    materialized via the canonical Pipeline 1 derivation
    (``germany_children_derived_facts_for_empty_household``). Production
    callers reach the real
    ``germany_2025_law.compute_germany_children_assessment_2025`` and
    fall back to disk loading.

    Authority: § 31 EStG / § 32 Abs. 6 EStG / BKGG. The boundary state
    must travel either through ``derived_facts`` or
    ``derived-facts.json`` — never via an in-memory fallback inside
    production code.
    """
    from tax_pipeline.y2025.germany_law import (
        compute_germany_children_assessment_2025 as
        _compute_germany_children_assessment_2025,
    )

    if derived_facts is None:
        derived_facts = germany_children_derived_facts_for_empty_household()
    return _compute_germany_children_assessment_2025(
        ordinary_taxable_income_eur=ordinary_taxable_income_eur,
        ordinary_income_tax_eur=ordinary_income_tax_eur,
        filing_posture=filing_posture,
        derived_facts=derived_facts,
    )


germany_model.compute_germany_children_assessment_2025 = (
    compute_germany_children_assessment_2025
)


class Germany2025LawTest(unittest.TestCase):
    def _seed_germany_inputs_tree(self, root: Path) -> YearPaths:
        return materialize_demo_workspace(root, demo_name="demo-2025", year=2025)

    def test_kirchensteuer_membership_required_in_profile(self) -> None:
        # § 51a EStG attaches Kirchensteuer for taxpayers in a recognized
        # Religionsgemeinschaft. The engine must require the profile to make
        # an explicit statement (membership name or "none") rather than
        # silently assume non-membership.
        # https://www.gesetze-im-internet.de/estg/__51a.html
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_germany_inputs_tree(Path(tmp))
            profile = json.loads(paths.profile_path.read_text())
            del profile["elections"]["germany_kirchensteuer_membership"]
            paths.profile_path.write_text(json.dumps(profile, indent=2))

            with self.assertRaisesRegex(ValueError, "germany_kirchensteuer_membership"):
                load_joint_ordinary_inputs_2025(paths)

    def test_kirchensteuer_membership_in_religionsgemeinschaft_fails_closed(self) -> None:
        # If the taxpayer is a member of a Kirchensteuer-collecting
        # Religionsgemeinschaft (e.g. Evangelische Kirche, Römisch-Katholische
        # Kirche), the 8 % or 9 % surcharge applies and must not be silently
        # omitted. The 2025 model does not implement Kirchensteuer; fail closed.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_germany_inputs_tree(Path(tmp))
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["germany_kirchensteuer_membership"] = "EVK"
            paths.profile_path.write_text(json.dumps(profile, indent=2))

            with self.assertRaisesRegex(NotImplementedError, "Kirchensteuer"):
                load_joint_ordinary_inputs_2025(paths)

    def test_retirement_special_expense_cap_2025_matches_knappschaft_rv_components(self) -> None:
        # § 10 Abs. 3 Satz 1 EStG sets the retirement Sonderausgaben Höchstbetrag
        # equal to the maximum (employer + employee) annual contribution to the
        # knappschaftliche Rentenversicherung West for the assessment year:
        #   Höchstbetrag = BBG_knapp_RV_west × Beitragssatz_knapp_RV
        # 2025 components per BMAS Sozialversicherungsrechengrößen-Verordnung 2025:
        #   BBG knappschaftliche RV West = €118,800
        #   Beitragssatz knappschaftliche RV (gesamt) = 24.7 %
        #   → Höchstbetrag = €118,800 × 0.247 = €29,343.60 (rounded €29,344 by BMF)
        # Authority: § 10 Abs. 3 EStG and the 2025 SVRBezV.
        # https://www.gesetze-im-internet.de/estg/__10.html
        # https://www.bmas.de/DE/Service/Gesetze-und-Gesetzesvorhaben/sozialversicherungs-rechengroessen-2025.html
        from decimal import ROUND_HALF_UP

        bbg = RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR
        rate = RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025
        # BMF rounds the Höchstbetrag to whole euro (HALF_UP).
        computed = (bbg * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        self.assertEqual(computed, Decimal("29344"))
        self.assertEqual(RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR, Decimal("29344.00"))

    def _wage(
        self,
        owner: str,
        *,
        gross_wage_eur: str = "60000.00",
        withheld_wage_tax_eur: str = "0.00",
        withheld_solidarity_surcharge_eur: str = "0.00",
        employer_pension_contribution_eur: str = "0.00",
        employee_pension_contribution_eur: str = "0.00",
        employee_health_insurance_eur: str = "0.00",
        employee_nursing_care_insurance_eur: str = "0.00",
        employee_unemployment_insurance_eur: str = "0.00",
    ) -> WageFacts2025:
        return WageFacts2025(
            owner=owner,
            source_files=(f"{owner}.pdf",),
            gross_wage_eur=Decimal(gross_wage_eur),
            withheld_wage_tax_eur=Decimal(withheld_wage_tax_eur),
            withheld_solidarity_surcharge_eur=Decimal(withheld_solidarity_surcharge_eur),
            multiannual_wage_eur=Decimal("0.00"),
            employer_pension_contribution_eur=Decimal(employer_pension_contribution_eur),
            employee_pension_contribution_eur=Decimal(employee_pension_contribution_eur),
            employee_health_insurance_eur=Decimal(employee_health_insurance_eur),
            employee_nursing_care_insurance_eur=Decimal(employee_nursing_care_insurance_eur),
            employee_unemployment_insurance_eur=Decimal(employee_unemployment_insurance_eur),
        )

    def _person(
        self,
        slot: str,
        wage: WageFacts2025,
        *,
        home_office_days_without_visit: int = 0,
        home_office_days_with_visit: int = 0,
        manual_work_equipment_deduction_eur: str = "0.00",
        telecom_deduction_eur: str = "0.00",
        employment_legal_insurance_deduction_eur: str = "0.00",
        cross_border_tax_help_deduction_eur: str = "0.00",
        other_vorsorge_cap_eur: str = "1900.00",
    ) -> PersonOrdinaryInputs2025:
        return PersonOrdinaryInputs2025(
            slot=slot,
            order_label=slot.replace("_", " ").title(),
            display_name=slot.replace("_", " ").title(),
            owner=wage.owner,
            wage=wage,
            work_equipment_items=(),
            home_office_days_without_visit=home_office_days_without_visit,
            home_office_days_with_visit=home_office_days_with_visit,
            manual_work_equipment_deduction_eur=Decimal(manual_work_equipment_deduction_eur),
            telecom_deduction_eur=Decimal(telecom_deduction_eur),
            employment_legal_insurance_deduction_eur=Decimal(employment_legal_insurance_deduction_eur),
            cross_border_tax_help_deduction_eur=Decimal(cross_border_tax_help_deduction_eur),
            health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
            other_vorsorge_cap_eur=Decimal(other_vorsorge_cap_eur),
        )

    def test_single_person_assessment_uses_single_tariff_without_requiring_spouse(self) -> None:
        wage = WageFacts2025(
            owner="person_1",
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
        inputs = JointOrdinaryInputs2025(
            people=(
                PersonOrdinaryInputs2025(
                    slot="person_1",
                    order_label="Person 1",
                    display_name="Taylor Taxpayer",
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
                ),
            ),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
        )

        assessment = compute_joint_ordinary_assessment_2025(inputs)

        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("58734.00"))
        self.assertEqual(assessment.joint_income_tax_eur, german_income_tax_single_2025(Decimal("58734.00")))
        self.assertEqual(assessment.people[0].allowed_werbungskosten_eur, Decimal("1230.00"))

    def test_married_separate_assessment_uses_single_tariff_per_person(self) -> None:
        wage_1 = WageFacts2025(
            owner="person_1",
            source_files=("synthetic-1.pdf",),
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
        wage_2 = WageFacts2025(
            owner="person_2",
            source_files=("synthetic-2.pdf",),
            gross_wage_eur=Decimal("30000.00"),
            withheld_wage_tax_eur=Decimal("3000.00"),
            withheld_solidarity_surcharge_eur=Decimal("0.00"),
            multiannual_wage_eur=Decimal("0.00"),
            employer_pension_contribution_eur=Decimal("0.00"),
            employee_pension_contribution_eur=Decimal("0.00"),
            employee_health_insurance_eur=Decimal("0.00"),
            employee_nursing_care_insurance_eur=Decimal("0.00"),
            employee_unemployment_insurance_eur=Decimal("0.00"),
        )
        inputs = JointOrdinaryInputs2025(
            people=(
                PersonOrdinaryInputs2025(
                    slot="person_1",
                    order_label="Person 1",
                    display_name="Taylor Taxpayer",
                    owner="person_1",
                    wage=wage_1,
                    work_equipment_items=(),
                    home_office_days_without_visit=0,
                    home_office_days_with_visit=0,
                    manual_work_equipment_deduction_eur=Decimal("0.00"),
                    telecom_deduction_eur=Decimal("0.00"),
                    employment_legal_insurance_deduction_eur=Decimal("0.00"),
                    cross_border_tax_help_deduction_eur=Decimal("0.00"),
                    health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
                ),
                PersonOrdinaryInputs2025(
                    slot="person_2",
                    order_label="Person 2",
                    display_name="Morgan Taxpayer",
                    owner="person_2",
                    wage=wage_2,
                    work_equipment_items=(),
                    home_office_days_without_visit=0,
                    home_office_days_with_visit=0,
                    manual_work_equipment_deduction_eur=Decimal("0.00"),
                    telecom_deduction_eur=Decimal("0.00"),
                    employment_legal_insurance_deduction_eur=Decimal("0.00"),
                    cross_border_tax_help_deduction_eur=Decimal("0.00"),
                    health_insurance_sick_pay_reduction_rate=Decimal("0.04"),
                ),
            ),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            filing_posture="married_separate",
        )

        assessment = compute_joint_ordinary_assessment_2025(inputs)

        self.assertEqual(assessment.filing_posture, "married_separate")
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("87468.00"))
        self.assertEqual(
            assessment.joint_income_tax_eur,
            german_income_tax_single_2025(Decimal("58734.00"))
            + german_income_tax_single_2025(Decimal("28734.00")),
        )
        self.assertEqual(assessment.total_special_expenses_eur, Decimal("72.00"))

    def test_two_person_ordinary_assessment_requires_explicit_26_estg_posture(self) -> None:
        # § 26 Abs. 1-3 EStG requires spouse eligibility and an assessment election/default
        # before § 26b aggregation and § 32a Abs. 5 splitting can apply.
        with self.assertRaisesRegex(ValueError, "explicit Germany filing_posture"):
            compute_joint_ordinary_assessment_2025(
                JointOrdinaryInputs2025(
                    people=(
                        self._person("person_1", self._wage("person_1")),
                        self._person("person_2", self._wage("person_2")),
                    ),
                    other_income_22nr3_eur=Decimal("0.00"),
                    other_income_22nr3_threshold_eur=Decimal("256.00"),
                    prepayments_eur=Decimal("0.00"),
                )
            )

    def test_married_joint_core_requires_validated_26_estg_prerequisites(self) -> None:
        # § 26 Abs. 1-3 EStG eligibility is the legal gate before § 26b aggregation and
        # § 32a Abs. 5 splitting; direct core calls must not bypass loader validation.
        with self.assertRaisesRegex(ValueError, "validated § 26 EStG prerequisites"):
            compute_joint_ordinary_assessment_2025(
                JointOrdinaryInputs2025(
                    people=(
                        self._person("person_1", self._wage("person_1")),
                        self._person("person_2", self._wage("person_2")),
                    ),
                    other_income_22nr3_eur=Decimal("0.00"),
                    other_income_22nr3_threshold_eur=Decimal("256.00"),
                    prepayments_eur=Decimal("0.00"),
                    filing_posture="married_joint",
                )
            )

    def test_germany_law_spec_files_exist(self) -> None:
        expected = [
            GERMANY_LAW_SPEC_ROOT / "index.md",
            GERMANY_LAW_SPEC_ROOT / "basic_tariff.md",
            GERMANY_LAW_SPEC_ROOT / "split_tariff.md",
            GERMANY_LAW_SPEC_ROOT / "ordinary_soli.md",
            GERMANY_LAW_SPEC_ROOT / "other_income_22nr3.md",
            GERMANY_LAW_SPEC_ROOT / "capital_tax_ordering.md",
            GERMANY_LAW_SPEC_ROOT / "payments_and_crediting.md",
        ]
        for path in expected:
            self.assertTrue(path.exists(), path)

    def test_final_refund_spec_declares_bank_certificate_withholding_integrated(self) -> None:
        # § 20 Abs. 6/9, § 32d Abs. 5, and § 36 Abs. 2 Nr. 2 EStG require spouse
        # certificate capital income, foreign-tax credits, and withholding credits to
        # be modeled in one joint capital sequence, not as a post-hoc refund sidecar.
        text = (GERMANY_LAW_SPEC_ROOT / "final_refund_assembly.md").read_text()

        self.assertIn("domestic bank certificate", text.lower())
        self.assertIn("§ 36", text)
        self.assertIn("withholding", text.lower())
        self.assertNotIn("add the spouse bank certificate effect", text.lower())

    def test_germany_capital_guenstigerpruefung_must_be_explicit_for_capital_income(self) -> None:
        # § 32d Abs. 6 EStG is an application/election to include capital income
        # in the ordinary tariff when that is more favorable. The pipeline must not
        # silently skip or apply that branch when capital income exists.
        capital = SimpleNamespace(taxable_after_teilfreistellung_eur=Decimal("100.00"))

        with self.assertRaisesRegex(ValueError, "§ 32d Abs. 6.*capital_guenstigerpruefung_requested"):
            germany_model.ensure_capital_guenstigerpruefung_position_2025({}, capital)

        with self.assertRaisesRegex(NotImplementedError, "§ 32d Abs. 6.*not implemented"):
            germany_model.ensure_capital_guenstigerpruefung_position_2025(
                {"capital_guenstigerpruefung_requested": Decimal("1")},
                capital,
            )

        germany_model.ensure_capital_guenstigerpruefung_position_2025(
            {"capital_guenstigerpruefung_requested": Decimal("0")},
            capital,
        )

    def _seed_loader_fixture_year(self, paths: YearPaths) -> None:
        materialized = materialize_demo_workspace(paths.project_root, demo_name="demo-2025", year=paths.year)
        self.assertEqual(materialized.year_root, paths.year_root)

    def _seed_married_loader_fixture_year(self, paths: YearPaths) -> None:
        self._seed_loader_fixture_year(paths)
        profile = json.loads(paths.profile_path.read_text())
        profile["jurisdictions"]["germany"]["filing_posture"] = "married_joint"
        profile["household"]["marital_status_on_dec_31"] = "married"
        profile["household"]["germany_filing_status"] = "joint"
        profile["german_return"]["assume_joint_assessment_if_married"] = True
        profile["german_return"]["joint_assessment_prerequisites"] = {
            "joint_election": True,
            "married_or_registered_partners": True,
            "not_permanently_separated": True,
            "unrestricted_tax_liability": True,
        }
        profile["german_return"]["person_slots"] = [
            {
                "slot": "person_1",
                "order_label": "Person 1",
                "display_name": "Alex North",
                "owner": "person_1",
                "anlage_n_label": "Anlage N (Person 1)",
                "anlage_kap_label": "Anlage KAP - Person 1",
                "kap_lines": ["17", "19", "20", "23", "41"],
                "kap_raw_lines": [],
                "kap_posture": "Synthetic married fixture person 1.",
                "kap_notes": ["Synthetic public test fixture."],
            },
            {
                "slot": "person_2",
                "order_label": "Person 2",
                "display_name": "Jamie North",
                "owner": "person_2",
                "anlage_n_label": "Anlage N (Person 2)",
                "anlage_kap_label": "Anlage KAP - Person 2",
                "kap_lines": [],
                "kap_raw_lines": [],
                "kap_posture": "Synthetic married fixture person 2.",
                "kap_notes": ["Synthetic public test fixture."],
            },
        ]
        paths.profile_path.write_text(json.dumps(profile))
        people_rows = list(csv.DictReader(paths.people_path.read_text().splitlines()))
        fieldnames = list(people_rows[0].keys())
        if "german_other_vorsorge_cap_eur" not in fieldnames:
            fieldnames.insert(fieldnames.index("church_tax_applicable"), "german_other_vorsorge_cap_eur")
            for row in people_rows:
                row["german_other_vorsorge_cap_eur"] = "1900.00"
        by_person = {row["person_id"]: row for row in people_rows}
        by_person["person_1"]["german_other_vorsorge_cap_eur"] = "1900.00"
        by_person["person_2"] = {
            "person_id": "person_2",
            "display_name": "Jamie North",
            "first_name": "Jamie",
            "last_name": "North",
            "gender": "",
            "relationship_role": "spouse",
            "elster_order": "2",
            "us_filer": "false",
            "is_taxpayer": "false",
            "is_spouse": "true",
            "date_of_birth": "",
            "citizenship": "DE",
            "country_of_tax_residence": "DE",
            "german_tax_id": "",
            "us_ssn_or_itin": "",
            "nra_for_us_return": "true",
            "german_health_insurer": "",
            "german_statutory_health_with_sick_pay": "false",
            "german_other_vorsorge_cap_eur": "1900.00",
            "church_tax_applicable": "false",
        }
        people_buffer = io.StringIO(newline="")
        people_writer = csv.DictWriter(people_buffer, fieldnames=fieldnames, lineterminator="\n")
        people_writer.writeheader()
        people_writer.writerows([by_person["person_1"], by_person["person_2"]])
        paths.people_path.write_text(people_buffer.getvalue())
        wage_fact_path = paths.facts_root / "alex-north-wage.facts.json"
        wage_fact = json.loads(wage_fact_path.read_text())
        wage_fact["owner"] = "person_1"
        wage_fact_path.write_text(json.dumps(wage_fact))
        zero_wage = json.loads(wage_fact_path.read_text())
        zero_wage["owner"] = "person_2"
        zero_wage["relative_path"] = "germany/jamie-north-zero-lohnsteuer-2025.pdf"
        for fact in zero_wage["facts"]:
            fact["value"] = "0.00"
            fact["source"]["file"] = zero_wage["relative_path"]
        (paths.facts_root / "jamie-north-zero-wage.facts.json").write_text(json.dumps(zero_wage))

        overrides = json.loads(paths.manual_overrides_path.read_text())
        overrides["deductions"]["persons"] = {
            "person_1": {
                "home_office_days_without_first_workplace_visit": 0,
                "home_office_days_with_first_workplace_visit": 0,
                "manual_work_equipment_deduction_eur": "0.00",
                "telecom_deduction_eur": "0.00",
                "employment_legal_insurance_deduction_eur": "0.00",
                "cross_border_tax_help_deduction_eur": "0.00",
                "health_insurance_sick_pay_reduction_rate": "0.04",
                "work_equipment_items": ["management_book", "charger"],
            },
            "person_2": {
                "home_office_days_without_first_workplace_visit": 0,
                "home_office_days_with_first_workplace_visit": 0,
                "manual_work_equipment_deduction_eur": "0.00",
                "telecom_deduction_eur": "0.00",
                "employment_legal_insurance_deduction_eur": "0.00",
                "cross_border_tax_help_deduction_eur": "0.00",
                "health_insurance_sick_pay_reduction_rate": "0.00",
                "work_equipment_items": [],
            },
        }
        overrides["deductions"]["work_use_percentages"] = {
            "management_book": "1.00",
            "charger": "0.50",
        }
        paths.manual_overrides_path.write_text(json.dumps(overrides))
        (paths.facts_root / "de-equipment-source-facts.csv").write_text(
            "section,key,value,source,note\n"
            "equipment,management_book_amount_eur,100.00,synthetic,Book used for deduction tests.\n"
            "equipment,charger_amount_eur,20.00,synthetic,Charger used for deduction tests.\n"
        )

    def test_split_tariff_uses_2025_statutory_thresholds(self) -> None:
        self.assertEqual(german_income_tax_split_2025(Decimal("24192")), Decimal("0"))
        self.assertEqual(german_income_tax_split_2025(Decimal("157109.18")), Decimal("44160"))

    def test_soli_assessment_uses_2025_posture_thresholds_and_milderungszone(self) -> None:
        self.assertEqual(
            german_soli_assessment_2025(Decimal("19950"), filing_posture="single"),
            Decimal("0.00"),
        )
        self.assertEqual(
            german_soli_assessment_2025(Decimal("19951"), filing_posture="single"),
            Decimal("0.11"),
        )
        self.assertEqual(
            german_soli_assessment_2025(Decimal("29741"), filing_posture="single"),
            Decimal("1165.12"),
        )
        self.assertEqual(
            german_soli_assessment_2025(Decimal("39900"), filing_posture="married_joint"),
            Decimal("0.00"),
        )
        self.assertEqual(
            german_soli_assessment_2025(Decimal("44160"), filing_posture="married_joint"),
            Decimal("506.94"),
        )

    def test_exact_joint_assessment_matches_2025_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            assessment = compute_joint_ordinary_assessment_2025(load_joint_ordinary_inputs_2025(paths))
        self.assertEqual(assessment.joint_taxable_income_eur, Decimal("96758.40"))
        self.assertEqual(assessment.joint_income_tax_eur, Decimal("29726.00"))
        self.assertEqual(assessment.joint_solidarity_surcharge_eur, Decimal("1163.34"))
        self.assertEqual(assessment.ordinary_refund_before_capital_eur, Decimal("150.66"))

    def test_home_office_tagespauschale_caps_at_annual_maximum(self) -> None:
        self.assertEqual(home_office_tagespauschale_2025(156, 0), Decimal("936.00"))
        self.assertEqual(home_office_tagespauschale_2025(300, 0), Decimal("1260.00"))

    def test_home_office_visit_days_require_no_other_workplace_position(self) -> None:
        with self.assertRaisesRegex(ValueError, "no other workplace"):
            home_office_tagespauschale_2025(0, 1)

    def test_employee_retirement_deduction_does_not_double_count_employer_share(self) -> None:
        self.assertEqual(
            retirement_special_expense_deduction_2025(
                Decimal("5639.28"),
                Decimal("8983.80"),
            ),
            Decimal("5639.28"),
        )

    def test_employee_retirement_deduction_applies_2025_cap_before_employer_reduction(self) -> None:
        self.assertEqual(
            retirement_special_expense_deduction_2025(
                Decimal("40000.00"),
                Decimal("10000.00"),
            ),
            Decimal("19344.00"),
        )

    def test_joint_retirement_cap_is_doubled_household_cap_under_10_3_estg(self) -> None:
        # § 10 Abs. 3 EStG gives jointly assessed spouses the doubled 2025 cap of 58,688 EUR.
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage(
                            "person_1",
                            employee_pension_contribution_eur="70000.00",
                        ),
                    ),
                    self._person("person_2", self._wage("person_2")),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        self.assertEqual(assessment.retirement_contributions_eur, Decimal("58688.00"))

    def test_joint_retirement_cap_subtracts_total_employer_share_after_cap_under_10_3_estg(self) -> None:
        # § 10 Abs. 3 Sätze 1, 2, 5 und 6 EStG caps the combined spouse base first, then
        # subtracts tax-free § 3 Nr. 62 employer pension shares; allocation is only audit display.
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage("person_1", employer_pension_contribution_eur="40000.00"),
                    ),
                    self._person(
                        "person_2",
                        self._wage("person_2", employee_pension_contribution_eur="40000.00"),
                    ),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        self.assertEqual(assessment.retirement_contributions_eur, Decimal("18688.00"))

    def test_other_vorsorge_cap_is_used_only_after_basic_health_and_nursing(self) -> None:
        self.assertEqual(
            other_vorsorge_allowed_employee_2025(
                Decimal("14057.04"),
                Decimal("1255.80"),
            ),
            Decimal("0.00"),
        )
        self.assertEqual(
            other_vorsorge_allowed_employee_2025(
                Decimal("1242.46"),
                Decimal("146.17"),
            ),
            Decimal("146.17"),
        )

    def test_joint_other_vorsorge_cap_is_common_cap_under_10_4_estg(self) -> None:
        # § 10 Abs. 4 Satz 3-4 EStG uses one joint cap; basic health/nursing consumes it first.
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage("person_1", employee_health_insurance_eur="4000.00"),
                    ),
                    self._person(
                        "person_2",
                        self._wage("person_2", employee_unemployment_insurance_eur="1000.00"),
                    ),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        self.assertEqual(assessment.health_and_nursing_contributions_eur, Decimal("3840.00"))
        self.assertEqual(assessment.other_vorsorge_allowed_eur, Decimal("0.00"))

    def test_joint_other_vorsorge_cap_sums_each_spouse_10_4_cap_class(self) -> None:
        # § 10 Abs. 4 Sätze 1-3 EStG gives each spouse their own 1,900 EUR or 2,800 EUR cap
        # class; the joint cap is the sum, not always 1,900 EUR times spouse count.
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage("person_1", employee_unemployment_insurance_eur="4200.00"),
                        other_vorsorge_cap_eur="2800.00",
                    ),
                    self._person(
                        "person_2",
                        self._wage("person_2"),
                        other_vorsorge_cap_eur="1900.00",
                    ),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        self.assertEqual(assessment.other_vorsorge_allowed_eur, Decimal("4200.00"))

    def test_basic_health_deduction_reduces_statutory_health_for_sick_pay_component(self) -> None:
        self.assertEqual(
            deductible_basic_health_contribution_2025(
                Decimal("11278.68"),
                Decimal("2778.36"),
                statutory_health_sick_pay_reduction_rate=Decimal("0.04"),
            ),
            Decimal("13605.89"),
        )

    def test_home_office_days_reject_negative_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            home_office_tagespauschale_2025(-1, 0)
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            home_office_tagespauschale_2025(0, -1)

    def test_basic_health_deduction_rejects_invalid_sick_pay_rate(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be between 0 and 1 inclusive"):
            deductible_basic_health_contribution_2025(
                Decimal("11278.68"),
                Decimal("2778.36"),
                statutory_health_sick_pay_reduction_rate=Decimal("-0.01"),
            )
        with self.assertRaisesRegex(ValueError, "must be between 0 and 1 inclusive"):
            deductible_basic_health_contribution_2025(
                Decimal("11278.68"),
                Decimal("2778.36"),
                statutory_health_sick_pay_reduction_rate=Decimal("1.01"),
            )

    def test_other_income_22nr3_is_freigrenze_not_freibetrag(self) -> None:
        self.assertEqual(other_income_22nr3_taxable_2025(Decimal("255.99"), Decimal("256.00")), Decimal("0.00"))
        self.assertEqual(other_income_22nr3_taxable_2025(Decimal("256.00"), Decimal("256.00")), Decimal("256.00"))
        self.assertEqual(other_income_22nr3_taxable_2025(Decimal("293.48"), Decimal("256.00")), Decimal("293.48"))

    def test_joint_other_income_22nr3_freigrenze_applies_per_spouse(self) -> None:
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person("person_1", self._wage("person_1", gross_wage_eur="10000.00")),
                    self._person("person_2", self._wage("person_2", gross_wage_eur="10000.00")),
                ),
                other_income_22nr3_eur=Decimal("400.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
                other_income_22nr3_by_person_eur=(Decimal("200.00"), Decimal("200.00")),
            )
        )

        self.assertEqual(assessment.other_income_22nr3_taxable_eur, Decimal("0.00"))

    def test_joint_other_income_22nr3_requires_spouse_allocations_when_nonzero(self) -> None:
        with self.assertRaisesRegex(ValueError, "per-spouse § 22 Nr. 3 allocations"):
            compute_joint_ordinary_assessment_2025(
                JointOrdinaryInputs2025(
                    people=(
                        self._person("person_1", self._wage("person_1", gross_wage_eur="10000.00")),
                        self._person("person_2", self._wage("person_2", gross_wage_eur="10000.00")),
                    ),
                    other_income_22nr3_eur=Decimal("400.00"),
                    other_income_22nr3_threshold_eur=Decimal("256.00"),
                    prepayments_eur=Decimal("0.00"),
                    filing_posture="married_joint",
                    joint_assessment_prerequisites_validated=True,
                )
            )

    def test_other_income_22nr3_rejects_negative_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            other_income_22nr3_taxable_2025(Decimal("-1.00"), Decimal("256.00"))

    def test_capital_foreign_tax_credit_precedes_capital_soli(self) -> None:
        assessment = capital_tax_after_foreign_tax_credit_2025(
            Decimal("10409.91"),
            Decimal("44.35"),
            capital_tax_rate=Decimal("0.25"),
            soli_rate=Decimal("0.055"),
        )
        self.assertEqual(assessment.gross_income_tax_eur, Decimal("2602.48"))
        self.assertEqual(assessment.income_tax_after_foreign_credit_eur, Decimal("2558.13"))
        self.assertEqual(assessment.solidarity_surcharge_eur, Decimal("140.69"))
        self.assertEqual(assessment.total_tax_eur, Decimal("2698.82"))

    def test_capital_soli_disregards_fractional_cents(self) -> None:
        assessment = capital_tax_after_foreign_tax_credit_2025(
            Decimal("10.00"),
            Decimal("0.00"),
            capital_tax_rate=Decimal("0.25"),
            soli_rate=Decimal("0.055"),
        )

        self.assertEqual(assessment.solidarity_surcharge_eur, Decimal("0.13"))

    def test_capital_foreign_tax_credit_caps_at_gross_tax(self) -> None:
        assessment = capital_tax_after_foreign_tax_credit_2025(
            Decimal("100.00"),
            Decimal("99.00"),
            capital_tax_rate=Decimal("0.25"),
            soli_rate=Decimal("0.055"),
        )
        self.assertEqual(assessment.gross_income_tax_eur, Decimal("25.00"))
        self.assertEqual(assessment.foreign_tax_credit_eur, Decimal("25.00"))
        self.assertEqual(assessment.income_tax_after_foreign_credit_eur, Decimal("0.00"))
        self.assertEqual(assessment.solidarity_surcharge_eur, Decimal("0.00"))
        self.assertEqual(assessment.total_tax_eur, Decimal("0.00"))

    def test_capital_foreign_tax_credit_32d5_caps_each_item_and_refund_claim(self) -> None:
        credit = foreign_tax_credit_32d5_cap_2025(
            (
                (Decimal("280.00"), Decimal("110.00"), Decimal("0.00")),
                (Decimal("120.00"), Decimal("15.00"), Decimal("5.00")),
            ),
            capital_tax_rate=Decimal("0.25"),
        )

        self.assertEqual(credit, Decimal("80.00"))

    def test_bank_capital_certificate_integrates_into_joint_20_32d_36_sequence(self) -> None:
        # § 20 EStG puts German bank-certificate line 7 in the capital base, line 8 is
        # the stock-sale subset for § 20 Abs. 6 stock-loss ordering, § 32d Abs. 5 EStG
        # credits line 40 foreign tax inside the capital tax sequence, and § 36 Abs. 2
        # Nr. 2 EStG credits line 37/38 withholding only after the tax has been computed.
        assessment = compute_germany_capital_assessment_2025(
            GermanyCapitalAssessmentInputs2025(
                sale_facts=(),
                income_facts=(),
                bank_certificates=(
                    GermanyBankCapitalCertificate2025(
                        owner_slot="person_2",
                        certificate_id="upvest_lien_2025",
                        source_file="Lien-capital-annual_income_statement.pdf",
                        kap_line_7_income_eur=Decimal("189.28"),
                        kap_line_8_stock_gains_eur=Decimal("65.62"),
                        kap_line_17_saver_allowance_used_eur=Decimal("0.00"),
                        kap_line_37_kest_withheld_eur=Decimal("31.57"),
                        kap_line_38_soli_withheld_eur=Decimal("1.64"),
                        kap_line_40_foreign_tax_credited_eur=Decimal("15.78"),
                        kap_line_41_foreign_tax_not_credited_eur=Decimal("0.00"),
                    ),
                ),
                dher_stock_gain_eur=Decimal("0.00"),
                stock_loss_carryforward_2024_eur=Decimal("0.00"),
                saver_allowance_eur=Decimal("0.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
                treaty_dividend_credit_eur=Decimal("0.00"),
                fund_classification={},
            )
        )

        self.assertEqual(assessment.stock_gain, Decimal("65.62"))
        self.assertEqual(assessment.positive_income_total, Decimal("123.66"))
        self.assertEqual(assessment.combined_current_capital_eur, Decimal("189.28"))
        self.assertEqual(assessment.taxable_after_teilfreistellung_eur, Decimal("189.28"))
        self.assertEqual(assessment.foreign_tax_credit_cap_eur, Decimal("15.78"))
        self.assertEqual(assessment.capital_with_teilfreistellung.gross_income_tax_eur, Decimal("47.32"))
        self.assertEqual(assessment.capital_with_teilfreistellung.income_tax_after_foreign_credit_eur, Decimal("31.54"))
        self.assertEqual(assessment.capital_with_teilfreistellung.solidarity_surcharge_eur, Decimal("1.73"))
        self.assertEqual(assessment.domestic_capital_tax_withheld_eur, Decimal("31.57"))
        self.assertEqual(assessment.domestic_capital_soli_withheld_eur, Decimal("1.64"))
        self.assertEqual(assessment.domestic_capital_withholding_credit_eur, Decimal("33.21"))

    def test_us_treaty_dividend_credit_is_integrated_through_32d5(self) -> None:
        # DBA-USA Art. 10 limits the U.S. source-country tax on ordinary portfolio
        # dividends to 15%, and Art. 23(5)(a) makes Germany credit that source tax
        # through the German foreign-tax-credit mechanism. § 32d Abs. 5 EStG still
        # caps the credit per taxable dividend item/source, so this is not a second
        # post-§32d treaty subtraction.
        assessment = compute_germany_capital_assessment_2025(
            GermanyCapitalAssessmentInputs2025(
                sale_facts=(),
                income_facts=(
                    GermanyCapitalIncomeFact2025(
                        kind="dividend",
                        asset_bucket="cash",
                        symbol="US_DIV",
                        eur_amount=Decimal("1000.00"),
                        foreign_tax_item_id="us_dividend_1",
                    ),
                ),
                treaty_dividend_items=(
                    GermanyTreatyDividendItem2025(
                        item_id="us_dividend_1",
                        owner_slot="person_1",
                        gross_dividend_eur=Decimal("1000.00"),
                        german_taxable_dividend_eur=Decimal("1000.00"),
                        allocated_us_tax_paid_eur=Decimal("280.00"),
                        treaty_rate=Decimal("0.15"),
                        dividend_class="portfolio_dividend",
                    ),
                ),
                dher_stock_gain_eur=Decimal("0.00"),
                stock_loss_carryforward_2024_eur=Decimal("0.00"),
                saver_allowance_eur=Decimal("0.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
                treaty_dividend_credit_eur=Decimal("0.00"),
                fund_classification={},
            )
        )

        self.assertEqual(assessment.treaty_us_source_dividend_gross_eur, Decimal("1000.00"))
        self.assertEqual(assessment.treaty_us_source_dividend_precredit_tax_eur, Decimal("250.00"))
        self.assertEqual(assessment.treaty_us_source_dividend_allowed_us_tax_eur, Decimal("150.00"))
        self.assertEqual(assessment.treaty_us_source_dividend_credit_eur, Decimal("150.00"))
        self.assertEqual(assessment.explicit_foreign_tax_total, Decimal("150.00"))
        self.assertEqual(assessment.capital_with_teilfreistellung.gross_income_tax_eur, Decimal("250.00"))
        self.assertEqual(assessment.capital_with_teilfreistellung.foreign_tax_credit_eur, Decimal("150.00"))
        self.assertEqual(assessment.capital_tax_with_teilfreistellung_after_treaty_eur, Decimal("105.50"))

    def test_us_treaty_dividend_item_rejects_duplicate_generic_foreign_tax_row(self) -> None:
        # DBA-USA Art. 10/23 and § 32d Abs. 5 EStG allow one credit path for the
        # same U.S.-source dividend item. A generic foreign_tax row with the same
        # foreign_tax_item_id as a treaty dividend item is an ambiguous duplicate
        # claim and must fail closed instead of double-crediting the same item.
        # Sources: https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html
        # and https://www.gesetze-im-internet.de/estg/__32d.html.
        with self.assertRaisesRegex(ValueError, "duplicate.*treaty dividend.*foreign_tax"):
            compute_germany_capital_assessment_2025(
                GermanyCapitalAssessmentInputs2025(
                    sale_facts=(),
                    income_facts=(
                        GermanyCapitalIncomeFact2025(
                            kind="dividend",
                            asset_bucket="cash",
                            symbol="US_DIV",
                            eur_amount=Decimal("1000.00"),
                            foreign_tax_item_id="us_dividend_1",
                        ),
                        GermanyCapitalIncomeFact2025(
                            kind="foreign_tax",
                            asset_bucket="cash",
                            symbol="US_DIV",
                            eur_amount=Decimal("68.00"),
                            refund_entitlement_eur=Decimal("0.00"),
                            foreign_tax_item_id="us_dividend_1",
                        ),
                    ),
                    treaty_dividend_items=(
                        GermanyTreatyDividendItem2025(
                            item_id="us_dividend_1",
                            owner_slot="person_1",
                            gross_dividend_eur=Decimal("1000.00"),
                            german_taxable_dividend_eur=Decimal("1000.00"),
                            allocated_us_tax_paid_eur=Decimal("68.00"),
                            treaty_rate=Decimal("0.15"),
                            dividend_class="portfolio_dividend",
                        ),
                    ),
                    dher_stock_gain_eur=Decimal("0.00"),
                    stock_loss_carryforward_2024_eur=Decimal("0.00"),
                    saver_allowance_eur=Decimal("0.00"),
                    capital_tax_rate=Decimal("0.25"),
                    soli_rate=Decimal("0.055"),
                    treaty_dividend_credit_eur=Decimal("0.00"),
                    fund_classification={},
                )
            )

    def test_us_treaty_dividend_article_10_amount_is_derived_from_gross_and_rate(self) -> None:
        # DBA-USA Art. 10 fixes the supported portfolio-dividend source-country tax
        # ceiling at 15% of the gross dividend. DBA-USA Art. 23(5)(a) then sends that
        # Article 10 amount into Germany's § 32d Abs. 5 EStG item/source cap. A low
        # manual sidecar value must not silently reduce the treaty amount before the
        # statutory German cap is applied.
        # Sources: https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html
        # and https://www.gesetze-im-internet.de/estg/__32d.html.
        assessment = compute_germany_capital_assessment_2025(
            GermanyCapitalAssessmentInputs2025(
                sale_facts=(),
                income_facts=(
                    GermanyCapitalIncomeFact2025(
                        kind="dividend",
                        asset_bucket="cash",
                        symbol="US_DIV",
                        eur_amount=Decimal("1000.00"),
                        foreign_tax_item_id="us_dividend_1",
                    ),
                ),
                treaty_dividend_items=(
                    GermanyTreatyDividendItem2025(
                        item_id="us_dividend_1",
                        owner_slot="person_1",
                        gross_dividend_eur=Decimal("1000.00"),
                        german_taxable_dividend_eur=Decimal("1000.00"),
                        allocated_us_tax_paid_eur=Decimal("10.00"),
                        treaty_rate=Decimal("0.15"),
                        dividend_class="portfolio_dividend",
                    ),
                ),
                dher_stock_gain_eur=Decimal("0.00"),
                stock_loss_carryforward_2024_eur=Decimal("0.00"),
                saver_allowance_eur=Decimal("0.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
                treaty_dividend_credit_eur=Decimal("0.00"),
                fund_classification={},
            )
        )

        self.assertEqual(assessment.treaty_us_source_dividend_allowed_us_tax_eur, Decimal("150.00"))
        self.assertEqual(assessment.treaty_us_source_dividend_credit_eur, Decimal("150.00"))

    def test_us_treaty_dividend_export_uses_post_allowance_actual_32d5_result(self) -> None:
        # DBA-USA Art. 23 and IRS Pub. 514 worksheet lines 17/18 need Germany's tax
        # and residence-country credit on the same U.S.-source dividend stack. Because
        # § 20 Abs. 9 EStG applies the Sparer-Pauschbetrag before § 32d Abs. 1/5 EStG,
        # a fully sheltered dividend exports no German pre-credit tax and no applied
        # German credit for the U.S. worksheet.
        assessment = compute_germany_capital_assessment_2025(
            GermanyCapitalAssessmentInputs2025(
                sale_facts=(),
                income_facts=(
                    GermanyCapitalIncomeFact2025(
                        kind="dividend",
                        asset_bucket="cash",
                        symbol="US_DIV",
                        eur_amount=Decimal("1000.00"),
                        foreign_tax_item_id="us_dividend_1",
                    ),
                ),
                treaty_dividend_items=(
                    GermanyTreatyDividendItem2025(
                        item_id="us_dividend_1",
                        owner_slot="person_1",
                        gross_dividend_eur=Decimal("1000.00"),
                        german_taxable_dividend_eur=Decimal("1000.00"),
                        allocated_us_tax_paid_eur=Decimal("150.00"),
                        treaty_rate=Decimal("0.15"),
                        dividend_class="portfolio_dividend",
                    ),
                ),
                dher_stock_gain_eur=Decimal("0.00"),
                stock_loss_carryforward_2024_eur=Decimal("0.00"),
                saver_allowance_eur=Decimal("1000.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
                treaty_dividend_credit_eur=Decimal("0.00"),
                fund_classification={},
            )
        )

        self.assertEqual(assessment.capital_with_teilfreistellung.gross_income_tax_eur, Decimal("0.00"))
        self.assertEqual(assessment.capital_with_teilfreistellung.foreign_tax_credit_eur, Decimal("0.00"))
        self.assertEqual(assessment.treaty_us_source_dividend_precredit_tax_eur, Decimal("0.00"))
        self.assertEqual(assessment.treaty_us_source_dividend_credit_eur, Decimal("0.00"))

    def test_us_treaty_dividend_item_requires_matching_taxable_dividend(self) -> None:
        # DBA-USA Art. 23 relief applies to tax on the same U.S.-source dividend.
        # A treaty item that cannot be matched to a § 20 EStG taxable dividend by
        # foreign_tax_item_id must fail closed instead of creating a free credit.
        with self.assertRaisesRegex(ValueError, "matching taxable U.S.-source dividend"):
            compute_germany_capital_assessment_2025(
                GermanyCapitalAssessmentInputs2025(
                    sale_facts=(),
                    income_facts=(),
                    treaty_dividend_items=(
                        GermanyTreatyDividendItem2025(
                            item_id="missing_dividend",
                            owner_slot="person_1",
                            gross_dividend_eur=Decimal("1000.00"),
                            german_taxable_dividend_eur=Decimal("1000.00"),
                            allocated_us_tax_paid_eur=Decimal("150.00"),
                            treaty_rate=Decimal("0.15"),
                            dividend_class="portfolio_dividend",
                        ),
                    ),
                    dher_stock_gain_eur=Decimal("0.00"),
                    stock_loss_carryforward_2024_eur=Decimal("0.00"),
                    saver_allowance_eur=Decimal("0.00"),
                    capital_tax_rate=Decimal("0.25"),
                    soli_rate=Decimal("0.055"),
                    treaty_dividend_credit_eur=Decimal("0.00"),
                    fund_classification={},
                )
            )

    def test_us_treaty_dividend_item_rejects_stock_gain_classification(self) -> None:
        # DBA-USA Art. 10 is a dividend rule. Stock-sale gains are analyzed under
        # Art. 13 and cannot be pushed through the dividend credit path.
        with self.assertRaisesRegex(ValueError, "Unsupported U.S.-source treaty dividend class"):
            compute_germany_capital_assessment_2025(
                GermanyCapitalAssessmentInputs2025(
                    sale_facts=(),
                    income_facts=(
                        GermanyCapitalIncomeFact2025(
                            kind="dividend",
                            asset_bucket="cash",
                            symbol="US_DIV",
                            eur_amount=Decimal("1000.00"),
                            foreign_tax_item_id="us_dividend_1",
                        ),
                    ),
                    treaty_dividend_items=(
                        GermanyTreatyDividendItem2025(
                            item_id="us_dividend_1",
                            owner_slot="person_1",
                            gross_dividend_eur=Decimal("1000.00"),
                            german_taxable_dividend_eur=Decimal("1000.00"),
                            allocated_us_tax_paid_eur=Decimal("150.00"),
                            treaty_rate=Decimal("0.15"),
                            dividend_class="stock_gain",
                        ),
                    ),
                    dher_stock_gain_eur=Decimal("0.00"),
                    stock_loss_carryforward_2024_eur=Decimal("0.00"),
                    saver_allowance_eur=Decimal("0.00"),
                    capital_tax_rate=Decimal("0.25"),
                    soli_rate=Decimal("0.055"),
                    treaty_dividend_credit_eur=Decimal("0.00"),
                    fund_classification={},
                )
            )

    def test_bank_capital_certificate_line_8_cannot_exceed_line_7(self) -> None:
        # Anlage KAP line 8 is a stock-gain subset of line 7; treating it as an
        # independent amount would double count capital income under § 20 EStG.
        with self.assertRaisesRegex(ValueError, "kap_line_8_stock_gains_eur"):
            compute_germany_capital_assessment_2025(
                GermanyCapitalAssessmentInputs2025(
                    sale_facts=(),
                    income_facts=(),
                    bank_certificates=(
                        GermanyBankCapitalCertificate2025(
                            owner_slot="person_2",
                            certificate_id="bad_cert",
                            source_file="bad.pdf",
                            kap_line_7_income_eur=Decimal("10.00"),
                            kap_line_8_stock_gains_eur=Decimal("10.01"),
                        ),
                    ),
                    dher_stock_gain_eur=Decimal("0.00"),
                    stock_loss_carryforward_2024_eur=Decimal("0.00"),
                    saver_allowance_eur=Decimal("0.00"),
                    capital_tax_rate=Decimal("0.25"),
                    soli_rate=Decimal("0.055"),
                    treaty_dividend_credit_eur=Decimal("0.00"),
                    fund_classification={},
                )
            )

    def test_legacy_spouse_bank_certificate_rows_load_as_typed_certificate(self) -> None:
        # Legacy extracted certificate rows still represent typed § 20/§ 32d/§ 36
        # legal facts. The loader must map them into a certificate object instead of
        # leaving them as ad-hoc spouse sidecar keys.
        with tempfile.TemporaryDirectory() as tmp:
            certificate_csv = Path(tmp) / "de-spouse-bank-capital-certificate.csv"
            certificate_csv.write_text(
                "section,key,value,source,note\n"
                "spouse_bank_capital,lien_bank_kap_income_eur,189.28,Lien-capital-annual_income_statement.pdf,line 7\n"
                "spouse_bank_capital,lien_bank_kap_stock_gain_eur,65.62,Lien-capital-annual_income_statement.pdf,line 8\n"
                "spouse_bank_capital,lien_bank_kest_withheld_eur,31.57,Lien-capital-annual_income_statement.pdf,line 37\n"
                "spouse_bank_capital,lien_bank_soli_withheld_eur,1.64,Lien-capital-annual_income_statement.pdf,line 38\n"
                "spouse_bank_capital,lien_bank_foreign_tax_credit_eur,15.78,Lien-capital-annual_income_statement.pdf,line 40\n"
                "spouse_bank_capital,lien_bank_sparer_pauschbetrag_used_eur,0.00,Lien-capital-annual_income_statement.pdf,line 17\n"
            )

            certificates = germany_model.load_bank_capital_certificates_2025(
                path=certificate_csv,
                person_slots=[
                    {"slot": "person_1", "anlage_kap_label": "Anlage KAP - Brenn"},
                    {"slot": "person_2", "anlage_kap_label": "Anlage KAP - Lien"},
                ],
            )

        self.assertEqual(len(certificates), 1)
        certificate = certificates[0]
        self.assertEqual(certificate.owner_slot, "person_2")
        self.assertEqual(certificate.certificate_id, "person_2_bank_certificate_1")
        self.assertEqual(certificate.source_file, "Lien-capital-annual_income_statement.pdf")
        self.assertEqual(certificate.kap_line_7_income_eur, Decimal("189.28"))
        self.assertEqual(certificate.kap_line_8_stock_gains_eur, Decimal("65.62"))
        self.assertEqual(certificate.kap_line_37_kest_withheld_eur, Decimal("31.57"))
        self.assertEqual(certificate.kap_line_38_soli_withheld_eur, Decimal("1.64"))
        self.assertEqual(certificate.kap_line_40_foreign_tax_credited_eur, Decimal("15.78"))

    def test_bank_certificate_loader_rejects_duplicate_aliases_for_same_typed_field(self) -> None:
        # § 20, § 32d Abs. 5, and § 36 Abs. 2 Nr. 2 EStG make bank-certificate
        # amounts legal facts. A typed certificate field must be exact-one; accepting
        # both legacy and canonical aliases would silently replace one legal input.
        with tempfile.TemporaryDirectory() as tmp:
            certificate_csv = Path(tmp) / "de-spouse-bank-capital-certificate.csv"
            certificate_csv.write_text(
                "section,key,value,source,note\n"
                "spouse_bank_capital,lien_bank_kap_income_eur,189.28,cert.pdf,line 7\n"
                "spouse_bank_capital,person_2_bank_certificate_kap_income_eur,200.00,cert.pdf,line 7 duplicate\n"
            )

            with self.assertRaisesRegex(ValueError, "Duplicate bank certificate field"):
                germany_model.load_bank_capital_certificates_2025(
                    path=certificate_csv,
                    person_slots=[
                        {"slot": "person_1", "anlage_kap_label": "Anlage KAP - Person 1"},
                        {"slot": "person_2", "anlage_kap_label": "Anlage KAP - Person 2"},
                    ],
                )

    def test_bank_certificate_loader_rejects_unknown_nonzero_certificate_facts(self) -> None:
        # § 36 Abs. 2 Nr. 2 EStG withholding credits and § 32d Abs. 5 foreign-tax
        # credits cannot be guessed from unknown certificate rows. Unsupported nonzero
        # rows must fail closed instead of being ignored.
        with tempfile.TemporaryDirectory() as tmp:
            certificate_csv = Path(tmp) / "de-spouse-bank-capital-certificate.csv"
            certificate_csv.write_text(
                "section,key,value,source,note\n"
                "spouse_bank_capital,lien_bank_kap_income_eur,189.28,cert.pdf,line 7\n"
                "spouse_bank_capital,lien_bank_unknown_withholding_eur,12.34,cert.pdf,unknown nonzero\n"
            )

            with self.assertRaisesRegex(ValueError, "Unsupported bank certificate key"):
                germany_model.load_bank_capital_certificates_2025(
                    path=certificate_csv,
                    person_slots=[
                        {"slot": "person_1", "anlage_kap_label": "Anlage KAP - Person 1"},
                        {"slot": "person_2", "anlage_kap_label": "Anlage KAP - Person 2"},
                    ],
                )

    def test_de_us_treaty_dividend_items_load_as_typed_article_10_facts(self) -> None:
        # DBA-USA Art. 10/23 dividend relief is a treaty fact, not a renderer
        # assumption. The loader must preserve item identity so § 32d Abs. 5 EStG
        # can cap the credit against the matching taxable dividend source.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "de-us-treaty-dividend-items.csv"
            path.write_text(
                "item_id,owner_slot,gross_dividend_eur,german_taxable_dividend_eur,allocated_us_tax_paid_eur,treaty_rate,dividend_class,source,note\n"
                "us_dividend_1,person_1,1000.00,1000.00,280.00,0.15,portfolio_dividend,broker_1099,Article 10 dividend\n"
            )

            items = germany_model.load_us_treaty_dividend_items_2025(path)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_id, "us_dividend_1")
        self.assertEqual(items[0].gross_dividend_eur, Decimal("1000.00"))
        self.assertEqual(items[0].allocated_us_tax_paid_eur, Decimal("280.00"))

    def test_capital_assessment_exposes_law_ordered_core_stages(self) -> None:
        # § 20 Abs. 6/9 EStG, InvStG § 20/§ 21, § 32d Abs. 1/5 EStG, and § 4 SolzG
        # are an ordered capital-income assessment, not pipeline-side arithmetic fragments.
        # The law core must expose those stages directly for audit and renderer reuse.
        assessment = compute_germany_capital_assessment_2025(
            GermanyCapitalAssessmentInputs2025(
                sale_facts=(
                    GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="ACME", gain_eur_matched=Decimal("1000.00")),
                    GermanyCapitalSaleFact2025(asset_bucket="fund_like", symbol="VTI", gain_eur_matched=Decimal("300.00")),
                ),
                income_facts=(
                    GermanyCapitalIncomeFact2025(kind="dividend", asset_bucket="fund_like", symbol="VTI", eur_amount=Decimal("120.00")),
                    GermanyCapitalIncomeFact2025(kind="dividend", asset_bucket="stock", symbol="FOREIGN", eur_amount=Decimal("100.00"), foreign_tax_item_id="div1"),
                    GermanyCapitalIncomeFact2025(
                        kind="foreign_tax",
                        asset_bucket="stock",
                        symbol="FOREIGN",
                        eur_amount=Decimal("40.00"),
                        refund_entitlement_eur=Decimal("10.00"),
                        foreign_tax_item_id="div1",
                    ),
                ),
                dher_stock_gain_eur=Decimal("0.00"),
                stock_loss_carryforward_2024_eur=Decimal("400.00"),
                saver_allowance_eur=Decimal("100.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
                treaty_dividend_credit_eur=Decimal("0.00"),
                fund_classification={"VTI": "aktienfonds"},
            )
        )

        # Phase 2 of the engine restructure: the canonical law-ordered audit
        # trace is the executed rule graph, not the legacy ``law_order_stages``
        # tuple. The graph executes DE25-13 through DE25-21 in declared order
        # (one stage per legal step from § 20 buckets through § 32d Abs. 1/5
        # tax to the DBA-USA Art. 23 fail-closed treaty check).
        from tax_pipeline.y2025.germany_capital_rules import (
            GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY,
        )
        from tax_pipeline.pipeline_context import get_pipeline_context_value
        execution = get_pipeline_context_value(GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY)
        self.assertIsNotNone(execution)
        self.assertEqual(
            [result.stage_id for result in execution.stage_results],
            [
                "DE25-13-CAPITAL-RAW-BUCKETS",
                # InvStG § 19 Vorabpauschale (laufender Ertrag) runs after
                # the raw-bucket assembly and before § 20 Abs. 6 EStG
                # netting (DE25-15) so the deemed-distribution amount can
                # join the non-stock-net bucket.
                # https://www.gesetze-im-internet.de/invstg_2018/__19.html
                "DE25-13F-VORABPAUSCHALE",
                "DE25-14-FUND-TEILFREISTELLUNG",
                "DE25-15-SECTION-20-6-NETTING",
                "DE25-16-SECTION-20-9-SAVER",
                "DE25-17-SECTION-32D1-GROSS-TAX",
                "DE25-18-SECTION-32D5-FTC",
                "DE25-19-CAPITAL-SOLI",
                "DE25-20-TREATY-CHECK",
                "DE25-21-FINAL-CAPITAL-TAX",
            ],
        )
        self.assertEqual(assessment.combined_current_capital_eur, Decimal("1120.00"))
        self.assertEqual(assessment.fund_taxable_after_teilfreistellung_eur, Decimal("294.00"))
        self.assertEqual(assessment.stock_loss_carryforward_used, Decimal("400.00"))
        self.assertEqual(assessment.taxable_after_teilfreistellung_eur, Decimal("894.00"))
        self.assertEqual(assessment.foreign_tax_credit_cap_eur, Decimal("25.00"))
        self.assertEqual(assessment.capital_tax_with_teilfreistellung_after_treaty_eur, Decimal("209.41"))

    def test_capital_assessment_rejects_unknown_sale_bucket_under_20_estg(self) -> None:
        # § 20 EStG, InvStG § 20/§ 21, and § 20 Abs. 6 EStG have bucket-specific
        # treatment. Unknown sale buckets must fail closed rather than falling out of
        # the Germany capital calculation.
        with self.assertRaisesRegex(ValueError, "Unsupported Germany capital sale asset_bucket"):
            compute_germany_capital_assessment_2025(
                GermanyCapitalAssessmentInputs2025(
                    sale_facts=(
                        GermanyCapitalSaleFact2025(
                            asset_bucket="mystery",
                            symbol="ACME",
                            gain_eur_matched=Decimal("1000.00"),
                        ),
                    ),
                    income_facts=(),
                    dher_stock_gain_eur=Decimal("0.00"),
                    stock_loss_carryforward_2024_eur=Decimal("0.00"),
                    saver_allowance_eur=Decimal("0.00"),
                    capital_tax_rate=Decimal("0.25"),
                    soli_rate=Decimal("0.055"),
                    treaty_dividend_credit_eur=Decimal("0.00"),
                    fund_classification={},
                )
            )

    def test_capital_assessment_rejects_unknown_income_classification_under_20_estg(self) -> None:
        # § 20 EStG identifies taxable capital-income kinds and § 32d Abs. 5 EStG
        # caps foreign tax by taxable item/source. Unknown income kinds or buckets
        # must fail closed before they can distort the item-level tax base.
        test_cases = [
            (
                GermanyCapitalIncomeFact2025(
                    kind="rebate",
                    asset_bucket="stock",
                    symbol="ACME",
                    eur_amount=Decimal("10.00"),
                ),
                "Unsupported Germany capital income kind",
            ),
            (
                GermanyCapitalIncomeFact2025(
                    kind="dividend",
                    asset_bucket="crypto",
                    symbol="BTC",
                    eur_amount=Decimal("10.00"),
                ),
                "Unsupported Germany capital income asset_bucket",
            ),
        ]
        for fact, message in test_cases:
            with self.subTest(kind=fact.kind, asset_bucket=fact.asset_bucket):
                with self.assertRaisesRegex(ValueError, message):
                    compute_germany_capital_assessment_2025(
                        GermanyCapitalAssessmentInputs2025(
                            sale_facts=(),
                            income_facts=(fact,),
                            dher_stock_gain_eur=Decimal("0.00"),
                            stock_loss_carryforward_2024_eur=Decimal("0.00"),
                            saver_allowance_eur=Decimal("0.00"),
                            capital_tax_rate=Decimal("0.25"),
                            soli_rate=Decimal("0.055"),
                            treaty_dividend_credit_eur=Decimal("0.00"),
                            fund_classification={},
                        )
                    )

    def test_capital_assessment_rejects_negative_statutory_amounts(self) -> None:
        # § 20 Abs. 6 EStG loss carryforwards and § 20 Abs. 9 EStG saver allowance
        # are non-negative statutory amounts. Negative values must not increase the
        # capital tax base or taxable capital by arithmetic accident.
        for field_name in ("stock_loss_carryforward_2024_eur", "saver_allowance_eur"):
            kwargs = {
                "sale_facts": (
                    GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="ACME", gain_eur_matched=Decimal("1000.00")),
                ),
                "income_facts": (),
                "dher_stock_gain_eur": Decimal("0.00"),
                "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                "saver_allowance_eur": Decimal("0.00"),
                "capital_tax_rate": Decimal("0.25"),
                "soli_rate": Decimal("0.055"),
                "treaty_dividend_credit_eur": Decimal("0.00"),
                "fund_classification": {},
            }
            kwargs[field_name] = Decimal("-1.00")
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(ValueError, field_name):
                    compute_germany_capital_assessment_2025(GermanyCapitalAssessmentInputs2025(**kwargs))

    def test_ordinary_assessment_rejects_negative_source_amounts_before_math(self) -> None:
        # § 2 Abs. 2 EStG income calculation and § 36 Abs. 2 EStG crediting require
        # actual non-negative wage, withholding, prepayment, and deduction source facts.
        # The legal core must reject impossible source facts before applying allowances.
        base_inputs = JointOrdinaryInputs2025(
            people=(
                self._person(
                    "person_1",
                    self._wage("person_1", gross_wage_eur="60000.00", withheld_wage_tax_eur="12000.00"),
                    home_office_days_without_visit=0,
                    manual_work_equipment_deduction_eur="0.00",
                ),
            ),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_threshold_eur=Decimal("256.00"),
            prepayments_eur=Decimal("0.00"),
            filing_posture="single",
        )

        negative_person = replace(
            base_inputs.people[0],
            wage=replace(base_inputs.people[0].wage, gross_wage_eur=Decimal("-1.00")),
        )
        with self.assertRaisesRegex(ValueError, "gross_wage_eur"):
            compute_joint_ordinary_assessment_2025(replace(base_inputs, people=(negative_person,)))

        negative_days = replace(base_inputs.people[0], home_office_days_without_visit=-1)
        with self.assertRaisesRegex(ValueError, "home_office_days_without_visit"):
            compute_joint_ordinary_assessment_2025(replace(base_inputs, people=(negative_days,)))

        with self.assertRaisesRegex(ValueError, "prepayments_eur"):
            compute_joint_ordinary_assessment_2025(replace(base_inputs, prepayments_eur=Decimal("-1.00")))

    def test_saver_allowance_transfer_caps_negative_other_spouse_under_20_9_estg(self) -> None:
        # § 20 Abs. 9 Satz 3 EStG lets spouses transfer unused allowance, but a
        # negative spouse capital bucket cannot create more than the statutory joint
        # Sparer-Pauschbetrag.
        self.assertEqual(
            saver_allowance_for_spouse_20_9_2025(
                Decimal("2500.00"),
                Decimal("-500.00"),
                Decimal("2000.00"),
            ),
            Decimal("2000.00"),
        )

    def test_capital_buckets_add_current_year_stock_losses_to_carryforward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,ACME,-50.00\n"
            )
            income.write_text("date,kind,asset_bucket,symbol,eur_amount\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("10.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("2000.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    set(),
                )

        self.assertEqual(capital.stock_loss_carryforward_remaining, Decimal("60.00"))

    def test_capital_foreign_tax_credit_cap_ignores_saver_allowance_under_32d5_bmf_205(self) -> None:
        # § 32d Abs. 5 EStG caps creditable foreign tax on the individual taxable foreign
        # capital item. BMF Abgeltungsteuer Rn. 205 says the credit is not reduced by a
        # state/item-differentiated Freistellungsauftrag allocation.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,DOMESTIC,1000.00\n"
            )
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n"
                "2025-03-15,dividend,stock,FOREIGN,100.00\n"
                "2025-12-31,foreign_tax,stock,FOREIGN,25.00,0.00\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("100.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    set(),
                )

        self.assertEqual(capital.foreign_tax_credit_cap_eur, Decimal("25.00"))

    def test_stock_loss_carryforward_waits_until_current_year_other_capital_losses_are_net_under_20_6(self) -> None:
        # § 20 Abs. 6 EStG loss ordering uses current-year § 20 losses before consuming a
        # separately restricted prior stock-loss carryforward.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,ACME,100.00\n"
                "2025-06-01,option,PUT,-100.00\n"
            )
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("100.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {},
                )

        self.assertEqual(capital.stock_loss_carryforward_used, Decimal("0.00"))
        self.assertEqual(capital.stock_loss_carryforward_remaining, Decimal("100.00"))

    def test_stock_loss_carryforward_considers_dividends_before_current_nonstock_losses_under_20_6(self) -> None:
        # § 20 Abs. 6 EStG nets current-year non-stock losses against positive § 20 income
        # before consuming a prior-year stock-loss carryforward against stock gains.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,ACME,100.00\n"
                "2025-06-01,option,PUT,-100.00\n"
            )
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n"
                "2025-03-15,dividend,stock,DIV,100.00,\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("100.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {},
                )

        self.assertEqual(capital.stock_loss_carryforward_used, Decimal("100.00"))
        self.assertEqual(capital.stock_loss_carryforward_remaining, Decimal("0.00"))

    def test_capital_foreign_tax_credit_cap_uses_foreign_item_not_same_symbol_sale_gain(self) -> None:
        # § 32d Abs. 5 EStG caps foreign tax at 25% of each individual taxable foreign capital item.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,ACME,1000.00\n"
            )
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n"
                "2025-03-15,dividend,stock,ACME,100.00,\n"
                "2025-12-31,foreign_tax,stock,ACME,100.00,0.00\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {},
                )

        self.assertEqual(capital.foreign_tax_credit_cap_eur, Decimal("25.00"))

    def test_capital_foreign_tax_fallback_symbol_must_be_unambiguous_under_32d5(self) -> None:
        # § 32d Abs. 5 EStG applies a per-item/source cap. If multiple same-symbol items exist,
        # missing foreign_tax_item_id would pool items and hide an over-credit.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text("date,asset_bucket,symbol,gain_eur_matched\n")
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n"
                "2025-03-15,dividend,stock,ACME,100.00,\n"
                "2025-06-15,dividend,stock,ACME,100.00,\n"
                "2025-12-31,foreign_tax,stock,ACME,100.00,0.00\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
                self.assertRaisesRegex(ValueError, "foreign_tax_item_id"),
            ):
                germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {},
                )

    def test_capital_foreign_tax_credit_cap_uses_item_ids_not_symbol_aggregation(self) -> None:
        # § 32d Abs. 5 EStG caps credit at 25% of each individual taxable foreign capital item,
        # so two same-symbol dividends cannot be pooled to absorb tax from only one item.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text("date,asset_bucket,symbol,gain_eur_matched\n")
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur,foreign_tax_item_id\n"
                "2025-03-15,dividend,stock,ACME,100.00,,lot_a\n"
                "2025-06-15,dividend,stock,ACME,100.00,,lot_b\n"
                "2025-12-31,foreign_tax,stock,ACME,100.00,0.00,lot_a\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {},
                )

        self.assertEqual(capital.foreign_tax_credit_cap_eur, Decimal("25.00"))

    def test_unknown_fund_classification_fails_closed_under_invstg_20(self) -> None:
        # InvStG § 20 has different Teilfreistellung rates; unknown fund_like symbols must not default to Aktienfonds.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,fund_like,UNKNOWN,100.00\n"
            )
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
                self.assertRaisesRegex(ValueError, "Fund classification.*UNKNOWN"),
            ):
                germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {},
                )

    def test_fund_classification_applies_invstg_20_teilfreistellung_rates(self) -> None:
        # InvStG § 20: Aktienfonds 30%, Mischfonds 15%, Immobilienfonds 60%, foreign property 80%.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,fund_like,EQ,100.00\n"
                "2025-05-01,fund_like,MIX,100.00\n"
                "2025-05-01,fund_like,PROP,100.00\n"
                "2025-05-01,fund_like,FPROP,100.00\n"
                "2025-05-01,fund_like,OTHER,100.00\n"
            )
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {
                        "EQ": "aktienfonds",
                        "MIX": "mischfonds",
                        "PROP": "immobilienfonds",
                        "FPROP": "auslands_immobilienfonds",
                        "OTHER": "sonstige",
                    },
                )

        self.assertEqual(capital.equity_fund_total, Decimal("100.00"))
        self.assertEqual(capital.non_equity_fund_total, Decimal("400.00"))
        self.assertEqual(capital.fund_teilfreistellung_reduction_eur, Decimal("185.00"))

    def test_fund_cash_income_is_not_double_counted_after_invstg_20_teilfreistellung(self) -> None:
        # InvStG § 20/§ 21 applies Teilfreistellung to fund gain and fund income once; § 32d
        # then taxes that already-adjusted § 20 capital amount without re-adding fund income.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            results = root / "results.json"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,fund_like,VTI,300.00\n"
            )
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n"
                "2025-03-15,dividend,fund_like,VTI,120.00,\n"
                "2025-03-15,dividend,stock,CASH,280.00,\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
                mock.patch.object(germany_model, "RESULTS_JSON", results),
                mock.patch.object(germany_model, "TRACE_CSV", root / "trace.csv"),
                mock.patch.object(germany_model, "SUMMARY_MD", root / "summary.md"),
                mock.patch.object(germany_model, "AUDIT_NOTE_MD", root / "audit.md"),
                mock.patch.object(germany_model, "COINBASE_RESULTS_JSON", root / "missing-coinbase.json"),
                # Force the assessment-derived person-slots fallback in
                # ``germany_projections.person_slots_for_projection_2025``
                # so the test does not silently depend on whether the
                # caller has a ``~/taxes/2025/config/profile.json`` on
                # disk (and which person slots it declares).
                mock.patch.object(_germany_projections, "load_german_person_slots", side_effect=FileNotFoundError),
                mock.patch.object(germany_model, "load_joint_ordinary_inputs_2025", return_value=self._ordinary_inputs_for_germany_main()),
                mock.patch.object(germany_model, "compute_joint_ordinary_assessment_2025", return_value=self._ordinary_assessment_for_germany_main()),
                mock.patch.object(
                    germany_model,
                    "capital_tax_after_foreign_tax_credit_2025",
                    side_effect=AssertionError("pipeline must not recompute § 32d capital tax"),
                    create=True,
                ),
                mock.patch.object(
                    germany_model,
                    "treaty_relieved_capital_tax_2025",
                    side_effect=AssertionError("pipeline must not recompute treaty capital relief"),
                    create=True,
                ),
                mock.patch.object(germany_model, "load_inputs", return_value={
                    "saver_allowance_eur": Decimal("0.00"),
                    "capital_tax_rate": Decimal("0.25"),
                    "soli_rate": Decimal("0.055"),
                    "treaty_dividend_credit_eur": Decimal("0.00"),
                    "foreign_tax_1099_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kap_income_eur": Decimal("0.00"),
                    "person_2_bank_certificate_foreign_tax_credit_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kest_withheld_eur": Decimal("0.00"),
                    "person_2_bank_certificate_soli_withheld_eur": Decimal("0.00"),
                    "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                    "private_sale_loss_carryforward_2024_eur": Decimal("0.00"),
                    "private_sale_gains_2025_eur": Decimal("0.00"),
                    "other_income_22nr3_freigrenze_eur": Decimal("256.00"),
                    "capital_guenstigerpruefung_requested": Decimal("0"),
                }),
                mock.patch.object(germany_model, "load_coinbase_results", return_value={
                    "private_sale_result_eur": Decimal("0.00"),
                    "prior_private_sale_carryforward_eur": Decimal("0.00"),
                    "updated_private_sale_carryforward_eur": Decimal("0.00"),
                }),
                mock.patch.object(germany_model, "load_dher_results", return_value={"total_gain_eur": Decimal("0.00")}),
                mock.patch.object(germany_model, "load_fund_classification", return_value={"VTI": "aktienfonds"}),
                mock.patch.object(germany_model, "compute_germany_vanilla_checkpoint_2025", return_value=self._vanilla_checkpoint_for_germany_main()),
            ):
                germany_model.main()

            payload = json.loads(results.read_text())

        self.assertEqual(payload["capital"]["fund_taxable_after_teilfreistellung_eur"], "294.00")
        self.assertEqual(payload["capital"]["taxable_after_teilfreistellung_eur"], "574.00")

    def test_fund_losses_are_reduced_by_teilfreistellung_under_invstg_21(self) -> None:
        # InvStG § 21 disallows the same percentage of fund-related losses/deductions as the
        # § 20 Teilfreistellung rate, so an Aktienfonds loss offsets only 70% of other gains.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,ACME,1000.00\n"
                "2025-06-01,fund_like,EQ,-1000.00\n"
            )
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {"EQ": "aktienfonds"},
                )

        self.assertEqual(capital.fund_taxable_after_teilfreistellung_eur, Decimal("-700.00"))

    def test_saver_allowance_uses_net_capital_after_fund_loss_teilfreistellung(self) -> None:
        # § 20 Abs. 9 EStG applies the Sparer-Pauschbetrag to net capital income after
        # InvStG § 21 has limited deductible fund losses, not to pre-netting positive symbols.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text(
                "date,asset_bucket,symbol,gain_eur_matched\n"
                "2025-05-01,stock,ACME,1000.00\n"
                "2025-06-01,fund_like,EQ,-1000.00\n"
            )
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
            ):
                capital = germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("2000.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    {"EQ": "aktienfonds"},
                )

        self.assertEqual(capital.saver_allowance_used_eur, Decimal("300.00"))

    def test_capital_foreign_tax_rows_require_refund_entitlement_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            sales.write_text("date,asset_bucket,symbol,gain_eur_matched\n")
            income.write_text(
                "date,kind,asset_bucket,symbol,eur_amount\n"
                "2025-12-31,foreign_tax,stock,FOREIGN,25.00\n"
            )

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
                self.assertRaisesRegex(ValueError, "refund_entitlement_eur"),
            ):
                germany_model.compute_capital_buckets(
                    {
                        "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                        "capital_tax_rate": Decimal("0.25"),
                        "saver_allowance_eur": Decimal("0.00"),
                    },
                    {"total_gain_eur": Decimal("0.00")},
                    set(),
                )

    def test_capital_foreign_tax_credit_rejects_negative_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "foreign_tax_credit_eur must be non-negative"):
            capital_tax_after_foreign_tax_credit_2025(
                Decimal("100.00"),
                Decimal("-1.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
            )

    def test_separate_germany_treaty_dividend_credit_is_not_a_second_capital_credit(self) -> None:
        with self.assertRaisesRegex(NotImplementedError, "Manual Germany treaty dividend credits are not supported"):
            treaty_relieved_capital_tax_2025(
                Decimal("500.00"),
                Decimal("27.50"),
                Decimal("10.00"),
            )

    def test_zero_treaty_credit_leaves_capital_liability_unchanged(self) -> None:
        relieved = treaty_relieved_capital_tax_2025(
            Decimal("20.00"),
            Decimal("1.10"),
            Decimal("0.00"),
        )
        self.assertEqual(relieved.solidarity_surcharge_after_treaty_eur, Decimal("1.10"))
        self.assertEqual(relieved.income_tax_after_treaty_eur, Decimal("20.00"))
        self.assertEqual(relieved.total_tax_after_treaty_eur, Decimal("21.10"))

    def _ordinary_assessment_for_germany_main(self) -> SimpleNamespace:
        def person(slot: str) -> SimpleNamespace:
            return SimpleNamespace(
                slot=slot,
                order_label=slot.replace("_", " ").title(),
                wage=self._wage(slot, gross_wage_eur="0.00"),
                work_equipment_items=(),
                manual_work_equipment_deduction_eur=Decimal("0.00"),
                work_equipment_eur=Decimal("0.00"),
                home_office_days_without_visit=0,
                home_office_days_with_visit=0,
                home_office_deduction_eur=Decimal("0.00"),
                telecom_deduction_eur=Decimal("0.00"),
                employment_legal_insurance_deduction_eur=Decimal("0.00"),
                cross_border_tax_help_deduction_eur=Decimal("0.00"),
                actual_werbungskosten_eur=Decimal("0.00"),
                allowed_werbungskosten_eur=Decimal("0.00"),
                income_after_werbungskosten_eur=Decimal("0.00"),
                employer_pension_contribution_eur=Decimal("0.00"),
                employee_pension_contribution_eur=Decimal("0.00"),
                retirement_contributions_eur=Decimal("0.00"),
                health_and_nursing_contributions_eur=Decimal("0.00"),
                other_vorsorge_contributions_eur=Decimal("0.00"),
                other_vorsorge_allowed_eur=Decimal("0.00"),
                total_special_expenses_eur=Decimal("0.00"),
            )

        return SimpleNamespace(
            filing_posture="married_joint",
            people=[person("person_1"), person("person_2")],
            ordinary_refund_before_capital_eur=Decimal("0.00"),
            joint_taxable_income_eur=Decimal("0.00"),
            joint_income_tax_eur=Decimal("0.00"),
            joint_solidarity_surcharge_eur=Decimal("0.00"),
            withheld_wage_tax_eur=Decimal("0.00"),
            withheld_wage_solidarity_surcharge_eur=Decimal("0.00"),
            prepayments_eur=Decimal("0.00"),
            sum_income_after_werbungskosten_eur=Decimal("0.00"),
            health_and_nursing_contributions_eur=Decimal("0.00"),
            total_special_expenses_eur=Decimal("0.00"),
            other_income_22nr3_eur=Decimal("0.00"),
            other_income_22nr3_taxable_eur=Decimal("0.00"),
            other_income_22nr3_by_person_taxable_eur=(Decimal("0.00"), Decimal("0.00")),
        )

    def _ordinary_inputs_for_germany_main(self) -> SimpleNamespace:
        return SimpleNamespace(
            people=(
                self._person("person_1", self._wage("person_1", gross_wage_eur="0.00")),
                self._person("person_2", self._wage("person_2", gross_wage_eur="0.00")),
            ),
            prepayments_eur=Decimal("0.00"),
        )

    def _vanilla_checkpoint_for_germany_main(self) -> SimpleNamespace:
        return SimpleNamespace(
            taxable_income_eur=Decimal("0.00"),
            income_tax_eur=Decimal("0.00"),
            soli_eur=Decimal("0.00"),
            total_tax_eur=Decimal("0.00"),
            refund_or_balance_due_eur=Decimal("0.00"),
        )

    def test_germany_model_final_result_integrates_bank_certificate_withholding_under_36(self) -> None:
        # § 20/§ 32d EStG compute tax on the typed bank certificate inside the capital
        # package; § 36 Abs. 2 Nr. 2 EStG then credits KEST/soli withholding after the
        # tax calculation instead of adding a post-hoc spouse sidecar effect.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            results = root / "results.json"
            sales.write_text("date,asset_bucket,symbol,gain_eur_matched\n")
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur,foreign_tax_item_id\n")
            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
                mock.patch.object(germany_model, "RESULTS_JSON", results),
                mock.patch.object(germany_model, "TRACE_CSV", root / "trace.csv"),
                mock.patch.object(germany_model, "SUMMARY_MD", root / "summary.md"),
                mock.patch.object(germany_model, "AUDIT_NOTE_MD", root / "audit.md"),
                mock.patch.object(germany_model, "COINBASE_RESULTS_JSON", root / "missing-coinbase.json"),
                # Force the assessment-derived person-slots fallback in
                # ``germany_projections.person_slots_for_projection_2025``
                # so the test does not silently depend on whether the
                # caller has a ``~/taxes/2025/config/profile.json`` on
                # disk (and which person slots it declares).
                mock.patch.object(_germany_projections, "load_german_person_slots", side_effect=FileNotFoundError),
                mock.patch.object(germany_model, "load_joint_ordinary_inputs_2025", return_value=self._ordinary_inputs_for_germany_main()),
                mock.patch.object(germany_model, "compute_joint_ordinary_assessment_2025", return_value=self._ordinary_assessment_for_germany_main()),
                mock.patch.object(germany_model, "load_inputs", return_value={
                    "saver_allowance_eur": Decimal("0.00"),
                    "capital_tax_rate": Decimal("0.25"),
                    "soli_rate": Decimal("0.055"),
                    "treaty_dividend_credit_eur": Decimal("0.00"),
                    "foreign_tax_1099_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kap_income_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kap_stock_gain_eur": Decimal("0.00"),
                    "person_2_bank_certificate_sparer_pauschbetrag_used_eur": Decimal("0.00"),
                    "person_2_bank_certificate_foreign_tax_credit_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kest_withheld_eur": Decimal("0.00"),
                    "person_2_bank_certificate_soli_withheld_eur": Decimal("0.00"),
                    "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                    "private_sale_loss_carryforward_2024_eur": Decimal("0.00"),
                    "private_sale_gains_2025_eur": Decimal("0.00"),
                    "other_income_22nr3_freigrenze_eur": Decimal("256.00"),
                    "capital_guenstigerpruefung_requested": Decimal("0"),
                }),
                mock.patch.object(germany_model, "load_coinbase_results", return_value={
                    "private_sale_result_eur": Decimal("0.00"),
                    "prior_private_sale_carryforward_eur": Decimal("0.00"),
                    "updated_private_sale_carryforward_eur": Decimal("0.00"),
                }),
                mock.patch.object(germany_model, "load_dher_results", return_value={"total_gain_eur": Decimal("0.00")}),
                mock.patch.object(germany_model, "load_bank_capital_certificates_2025", return_value=(
                    GermanyBankCapitalCertificate2025(
                        owner_slot="person_2",
                        certificate_id="upvest_lien_2025",
                        source_file="Lien-capital-annual_income_statement.pdf",
                        kap_line_7_income_eur=Decimal("189.28"),
                        kap_line_8_stock_gains_eur=Decimal("65.62"),
                        kap_line_37_kest_withheld_eur=Decimal("31.57"),
                        kap_line_38_soli_withheld_eur=Decimal("1.64"),
                        kap_line_40_foreign_tax_credited_eur=Decimal("15.78"),
                    ),
                )),
                mock.patch.object(germany_model, "load_fund_classification", return_value={}),
                mock.patch.object(germany_model, "compute_germany_vanilla_checkpoint_2025", return_value=self._vanilla_checkpoint_for_germany_main()),
            ):
                germany_model.main()

            payload = json.loads(results.read_text())

        self.assertEqual(payload["capital"]["bank_certificate_income_eur"], "189.28")
        self.assertEqual(payload["capital"]["domestic_capital_withholding_credit_eur"], "33.21")
        self.assertEqual(payload["refunds"]["final_target_refund_eur"], "-0.06")
        self.assertNotIn("person_2_bank_certificate_refund_effect_eur", payload["refunds"])
        kap_rows = {
            (row[0], row[1]): row[2]
            for row in payload["render_projection"]["elster"]["kap_summary_rows"]
        }
        self.assertEqual(kap_rows[("Anlage KAP (Person 2)", "7")], "189.28")
        self.assertEqual(kap_rows[("Anlage KAP (Person 2)", "8")], "65.62")
        self.assertEqual(kap_rows[("Anlage KAP (Person 2)", "37")], "31.57")
        self.assertEqual(kap_rows[("Anlage KAP (Person 2)", "38")], "1.64")
        self.assertEqual(kap_rows[("Anlage KAP (Person 2)", "40")], "15.78")

    def test_joint_vorsorge_and_sonderausgaben_pauschbetrag_are_separate_deductions(self) -> None:
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage(
                            "person_1",
                            employee_health_insurance_eur="1000.00",
                            employee_nursing_care_insurance_eur="100.00",
                        ),
                    ),
                    self._person("person_2", self._wage("person_2")),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        self.assertEqual(assessment.health_and_nursing_contributions_eur, Decimal("1060.00"))
        self.assertEqual(assessment.total_special_expenses_eur, Decimal("1132.00"))

    def test_employee_lump_sum_is_capped_at_each_spouses_wage_receipts(self) -> None:
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person("person_1", self._wage("person_1", gross_wage_eur="60000.00")),
                    self._person("person_2", self._wage("person_2", gross_wage_eur="0.00")),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        person_2 = next(person for person in assessment.people if person.slot == "person_2")
        self.assertEqual(person_2.allowed_werbungskosten_eur, Decimal("0.00"))
        self.assertEqual(person_2.income_after_werbungskosten_eur, Decimal("0.00"))

    def test_wage_withholding_credits_round_up_to_full_euros(self) -> None:
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage(
                            "person_1",
                            gross_wage_eur="0.00",
                            withheld_wage_tax_eur="100.01",
                            withheld_solidarity_surcharge_eur="1.01",
                        ),
                    ),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="single",
            )
        )

        self.assertEqual(assessment.withheld_wage_tax_eur, Decimal("101.00"))
        self.assertEqual(assessment.withheld_wage_solidarity_surcharge_eur, Decimal("2.00"))
        self.assertEqual(assessment.ordinary_refund_before_capital_eur, Decimal("103.00"))

    def test_joint_wage_withholding_rounds_each_abzugsteuer_sum_under_36_3_estg(self) -> None:
        # § 36 Abs. 3 EStG rounds the sum of each withholding-tax type, not each spouse first.
        assessment = compute_joint_ordinary_assessment_2025(
            JointOrdinaryInputs2025(
                people=(
                    self._person(
                        "person_1",
                        self._wage(
                            "person_1",
                            gross_wage_eur="0.00",
                            withheld_wage_tax_eur="100.01",
                            withheld_solidarity_surcharge_eur="1.01",
                        ),
                    ),
                    self._person(
                        "person_2",
                        self._wage(
                            "person_2",
                            gross_wage_eur="0.00",
                            withheld_wage_tax_eur="100.01",
                            withheld_solidarity_surcharge_eur="1.01",
                        ),
                    ),
                ),
                other_income_22nr3_eur=Decimal("0.00"),
                other_income_22nr3_threshold_eur=Decimal("256.00"),
                prepayments_eur=Decimal("0.00"),
                filing_posture="married_joint",
                joint_assessment_prerequisites_validated=True,
            )
        )

        self.assertEqual(assessment.withheld_wage_tax_eur, Decimal("201.00"))
        self.assertEqual(assessment.withheld_wage_solidarity_surcharge_eur, Decimal("3.00"))

    def test_missing_person_slots_raises_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()
            paths.profile_path.write_text(json.dumps({"german_return": {}}))

            with self.assertRaisesRegex(ValueError, "Missing or empty german_return.person_slots config"):
                load_joint_ordinary_inputs_2025(paths)

    def test_married_joint_loader_requires_explicit_26_estg_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            profile = json.loads(paths.profile_path.read_text())
            profile["german_return"].pop("joint_assessment_prerequisites", None)
            paths.profile_path.write_text(json.dumps(profile))

            with self.assertRaisesRegex(ValueError, "joint_assessment_prerequisites"):
                load_joint_ordinary_inputs_2025(paths)

    def test_married_joint_loader_accepts_default_joint_election_and_life_partner_status(self) -> None:
        # § 26 Abs. 3 EStG defaults to joint assessment; § 2 Abs. 8 EStG applies spouse rules to life partners.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            profile = json.loads(paths.profile_path.read_text())
            profile["household"]["marital_status_on_dec_31"] = "registered_partner"
            profile["german_return"]["joint_assessment_prerequisites"].pop("joint_election", None)
            profile["german_return"]["joint_assessment_prerequisites"][
                "eligibility_existed_at_start_or_arose_during_year"
            ] = True
            paths.profile_path.write_text(json.dumps(profile))

            inputs = load_joint_ordinary_inputs_2025(paths)

        self.assertEqual(inputs.filing_posture, "married_joint")
        self.assertTrue(inputs.joint_assessment_prerequisites_validated)

    def test_married_joint_loader_requires_distinct_non_empty_owners(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            profile = json.loads(paths.profile_path.read_text())
            profile["german_return"]["person_slots"][1]["owner"] = "person_1"
            paths.profile_path.write_text(json.dumps(profile))

            with self.assertRaisesRegex(ValueError, "distinct non-empty owner"):
                load_joint_ordinary_inputs_2025(paths)

    def test_germany_prepayments_require_eur_non_negative_amounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            paths.payments_path.write_text(
                "jurisdiction,person_id,payment_type,amount,currency,source,note\n"
                "germany,,income_tax_prepayment,-1.00,EUR,test,negative should fail\n"
            )

            with self.assertRaisesRegex(ValueError, "German income-tax prepayments must be non-negative EUR"):
                load_joint_ordinary_inputs_2025(paths)

    def test_germany_prepayments_reject_non_eur_currency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            paths.payments_path.write_text(
                "jurisdiction,person_id,payment_type,amount,currency,source,note\n"
                "germany,,income_tax_prepayment,1.00,USD,test,wrong currency should fail\n"
            )

            with self.assertRaisesRegex(ValueError, "German income-tax prepayments must be non-negative EUR"):
                load_joint_ordinary_inputs_2025(paths)

    def test_legacy_home_office_fallback_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["home_office_days"] = 10
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "Legacy deductions.home_office_days fallback is no longer supported"):
                load_joint_ordinary_inputs_2025(paths)

    def test_home_office_no_other_workplace_flag_must_be_literal_boolean_under_4_5_6c_estg(self) -> None:
        # § 4 Abs. 5 Satz 1 Nr. 6c EStG visit-day eligibility is a legal condition, not a truthy string.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["persons"]["person_1"]["home_office_days_with_first_workplace_visit"] = 1
            payload["deductions"]["persons"]["person_1"][
                "home_office_first_workplace_visit_days_have_no_other_workplace"
            ] = "false"
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "must be a boolean"):
                load_joint_ordinary_inputs_2025(paths)

    def test_statutory_sick_pay_people_fact_forces_10_1_3_sentence_4_reduction(self) -> None:
        # § 10 Abs. 1 Nr. 3 Satz 4 EStG requires the 4% reduction with Krankengeld entitlement.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            rows = list(csv.DictReader(paths.people_path.read_text().splitlines()))
            for row in rows:
                if row["person_id"] == "person_1":
                    row["german_statutory_health_with_sick_pay"] = "true"
            people_buffer = io.StringIO(newline="")
            writer = csv.DictWriter(people_buffer, fieldnames=rows[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            paths.people_path.write_text(people_buffer.getvalue())
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["persons"]["person_1"]["health_insurance_sick_pay_reduction_rate"] = "0.00"
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "§ 10 Abs. 1 Nr. 3 Satz 4"):
                load_joint_ordinary_inputs_2025(paths)

    def test_health_contributions_require_explicit_sick_pay_fact_under_10_1_3_sentence_4_estg(self) -> None:
        # § 10 Abs. 1 Nr. 3 Satz 4 EStG turns on the factual Krankengeld entitlement, so the
        # loader must not rely on a free manual reduction rate when health contributions exist.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            rows = list(csv.DictReader(paths.people_path.read_text().splitlines()))
            rows[0]["german_statutory_health_with_sick_pay"] = ""
            people_buffer = io.StringIO(newline="")
            writer = csv.DictWriter(people_buffer, fieldnames=rows[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            paths.people_path.write_text(people_buffer.getvalue())

            with self.assertRaisesRegex(ValueError, "german_statutory_health_with_sick_pay"):
                load_joint_ordinary_inputs_2025(paths)

    def test_other_vorsorge_cap_requires_explicit_people_fact_under_10_4_estg(self) -> None:
        # § 10 Abs. 4 EStG uses a person-specific 1,900 EUR or 2,800 EUR cap; the loader must
        # not assume the lower employee cap when the people.csv fact is missing.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            rows = list(csv.DictReader(paths.people_path.read_text().splitlines()))
            for row in rows:
                row["german_other_vorsorge_cap_eur"] = ""
            people_buffer = io.StringIO(newline="")
            writer = csv.DictWriter(people_buffer, fieldnames=rows[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            paths.people_path.write_text(people_buffer.getvalue())

            with self.assertRaisesRegex(ValueError, "german_other_vorsorge_cap_eur"):
                load_joint_ordinary_inputs_2025(paths)

    def test_missing_explicit_person_deduction_field_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            del payload["deductions"]["persons"]["person_2"]["telecom_deduction_eur"]
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "Missing deductions.persons.person_2.telecom_deduction_eur"):
                load_joint_ordinary_inputs_2025(paths)

    def test_drifted_freigrenze_row_fails_direct_ordinary_assessment(self) -> None:
        # F-DE-1 / Invariant I1: the workspace de-tax-constants.csv carries a
        # redundant declaration of § 22 Nr. 3 Satz 2 EStG €256 Freigrenze. The
        # canonical value lives in germany_2025_law.OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR;
        # a workspace edit that drifts must fail closed under
        # ``assert_germany_csv_statutory_constants_2025``.
        # Authority: § 22 Nr. 3 Satz 2 EStG —
        # https://www.gesetze-im-internet.de/estg/__22.html
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            (paths.derived_facts_root / "common" / "other-income-facts.csv").write_text(
                "section,key,value,source,note\n"
                "other_income,staking_income_eur,0.00,test,explicit zero staking row for threshold test\n"
            )
            (paths.reference_data_root / "de-tax-constants.csv").write_text(
                "section,key,value,source,note\n"
                "base,capital_tax_rate,0.25,src,note\n"
                "base,soli_rate,0.055,src,note\n"
                "base,saver_allowance_eur,2000.00,src,note\n"
                "base,other_income_22nr3_freigrenze_eur,300.00,src,drift\n"
            )
            with self.assertRaisesRegex(ValueError, "other_income_22nr3_freigrenze_eur"):
                load_joint_ordinary_inputs_2025(paths)

    def test_missing_staking_derived_facts_row_fails_direct_ordinary_assessment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_loader_fixture_year(paths)
            (paths.derived_facts_root / "common" / "other-income-facts.csv").write_text(
                "section,key,value,source,note\n"
            )

            with self.assertRaisesRegex(KeyError, "staking_income_eur"):
                load_joint_ordinary_inputs_2025(paths)

    def test_missing_equipment_assignment_raises_for_claimed_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["persons"]["person_1"]["work_equipment_items"] = []
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "not assigned to any person"):
                load_joint_ordinary_inputs_2025(paths)

    def test_missing_work_use_percentage_for_claimed_equipment_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["work_use_percentages"].pop("charger", None)
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "Missing work-use percentages for configured equipment items"):
                load_joint_ordinary_inputs_2025(paths)

    def test_high_value_equipment_requires_current_year_deduction_under_9_and_6_estg(self) -> None:
        # § 9 Abs. 1 Nr. 6-7 EStG imports AfA/GWG concepts; above the § 6 Abs. 2 GWG shortcut,
        # the source fact must provide the legally determined current-year deductible amount.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            (paths.facts_root / "de-equipment-source-facts.csv").write_text(
                "section,key,value,source,note\n"
                "equipment,management_book_amount_eur,1000.00,synthetic,Above GWG shortcut.\n"
                "equipment,charger_amount_eur,20.00,synthetic,Low-value charger.\n"
            )

            with self.assertRaisesRegex(ValueError, "current-year deductible"):
                load_joint_ordinary_inputs_2025(paths)

    def test_duplicate_equipment_assignment_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["persons"]["person_2"]["work_equipment_items"] = ["management_book"]
            paths.manual_overrides_path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(ValueError, "assigned to multiple people"):
                load_joint_ordinary_inputs_2025(paths)

    def test_manual_work_equipment_deduction_can_be_carried_by_person_2_without_invoice_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            self._seed_married_loader_fixture_year(paths)
            payload = json.loads(paths.manual_overrides_path.read_text())
            payload["deductions"]["persons"]["person_2"]["manual_work_equipment_deduction_eur"] = "110.00"
            paths.manual_overrides_path.write_text(json.dumps(payload))

            assessment = compute_joint_ordinary_assessment_2025(load_joint_ordinary_inputs_2025(paths))
            person_2 = next(person for person in assessment.people if person.slot == "person_2")

            self.assertEqual(person_2.manual_work_equipment_deduction_eur, Decimal("110.00"))
            self.assertEqual(person_2.work_equipment_eur, Decimal("110.00"))
            self.assertEqual(person_2.allowed_werbungskosten_eur, Decimal("110.00"))

    def test_germany_model_writes_audit_artifacts_with_legal_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            env = os.environ.copy()
            env.update(
                {
                    "TAX_PROJECT_ROOT": str(root),
                    "TAX_YEAR": "2025",
                    "TAX_WORKSPACE_ROOT": str(root / "years" / "2025"),
                    "TAX_USE_YEAR_LAYOUT": "1",
                }
            )
            # F-A4: Pipeline 2 (germany_model) reads derived-facts.json
            # written by Pipeline 1 (run_derivation). The fail-closed
            # boundary requires run_derivation to commit the artifact
            # before germany_model runs. Production orchestration
            # (run_year) chains them automatically; this subprocess test
            # invokes germany_model directly so it must run Pipeline 1
            # explicitly first.
            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.run_derivation"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )
            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.germany_model"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )

            trace_text = (root / "years" / "2025" / "outputs" / "analysis-steps" / "germany-model-trace.csv").read_text()
            audit_text = (root / "years" / "2025" / "outputs" / "analysis-steps" / "germany-audit-note.md").read_text()

        self.assertIn("joint_assessment_order", trace_text)
        self.assertIn("normalized/derived-facts/common/other-income-facts.csv", trace_text)
        self.assertIn("§ 10 Abs. 1 Nr. 3 Satz 4 EStG", audit_text)
        self.assertIn("tax_pipeline/y2025/germany_law.py", audit_text)
        self.assertIn("person_1_other_income_22nr3_taxable", trace_text)
        self.assertIn("sum_of_income", trace_text)
        self.assertIn("§ 2 Abs. 3 EStG", trace_text)
        self.assertIn("§ 36 Abs. 3 EStG", trace_text)
        self.assertIn("person_1_health_gross", trace_text)
        self.assertIn("person_1_health_sick_pay_reduction", trace_text)
        self.assertIn("joint_other_vorsorge_cap", trace_text)
        self.assertIn("§ 10 Abs. 4 Satz 3 und 4 EStG", trace_text)

    def test_single_person_spouse_bank_certificate_facts_fail_closed_under_36_estg(self) -> None:
        # § 36 Abs. 2 Nr. 2 EStG withholding credits belong to the person whose
        # certificate produced them. A single-person run must not silently drop
        # nonzero person_2 certificate facts.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "spouse-bank.csv"
            source.write_text(
                "category,key,value,source,line\n"
                "spouse_bank_capital,person_2_bank_certificate_kest_withheld_eur,10.01,Lien-capital.pdf,line 37\n"
            )
            with self.assertRaisesRegex(ValueError, "person_2 bank certificate"):
                germany_model.load_bank_capital_certificates_2025(
                    source,
                    person_slots=[{"slot": "person_1"}],
                )

    def test_positive_private_sale_sidecar_fails_closed_until_integrated_under_23_estg(self) -> None:
        # § 23 Abs. 3 EStG private-sale gains/losses affect the taxable result and cannot
        # remain an audit-only sidecar once the current-year result is positive.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales = root / "sales.csv"
            income = root / "income.csv"
            results = root / "results.json"
            sales.write_text("date,asset_bucket,symbol,gain_eur_matched\n")
            income.write_text("date,kind,asset_bucket,symbol,eur_amount,refund_entitlement_eur,foreign_tax_item_id\n")

            with (
                mock.patch.object(germany_model, "SALES_CSV", sales),
                mock.patch.object(germany_model, "INCOME_CSV", income),
                mock.patch.object(germany_model, "RESULTS_JSON", results),
                mock.patch.object(germany_model, "TRACE_CSV", root / "trace.csv"),
                mock.patch.object(germany_model, "SUMMARY_MD", root / "summary.md"),
                mock.patch.object(germany_model, "AUDIT_NOTE_MD", root / "audit.md"),
                mock.patch.object(germany_model, "COINBASE_RESULTS_JSON", root / "crypto-private-sales-results.json"),
                mock.patch.object(germany_model, "load_joint_ordinary_inputs_2025", return_value=self._ordinary_inputs_for_germany_main()),
                mock.patch.object(germany_model, "compute_joint_ordinary_assessment_2025", return_value=self._ordinary_assessment_for_germany_main()),
                mock.patch.object(germany_model, "load_inputs", return_value={
                    "saver_allowance_eur": Decimal("1000.00"),
                    "capital_tax_rate": Decimal("0.25"),
                    "soli_rate": Decimal("0.055"),
                    "treaty_dividend_credit_eur": Decimal("0.00"),
                    "foreign_tax_1099_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kap_income_eur": Decimal("0.00"),
                    "person_2_bank_certificate_foreign_tax_credit_eur": Decimal("0.00"),
                    "person_2_bank_certificate_kest_withheld_eur": Decimal("0.00"),
                    "person_2_bank_certificate_soli_withheld_eur": Decimal("0.00"),
                    "stock_loss_carryforward_2024_eur": Decimal("0.00"),
                    "private_sale_loss_carryforward_2024_eur": Decimal("0.00"),
                    "private_sale_gains_2025_eur": Decimal("0.00"),
                    "other_income_22nr3_freigrenze_eur": Decimal("256.00"),
                }),
                mock.patch.object(germany_model, "load_coinbase_results", return_value={
                    "private_sale_result_eur": Decimal("12.34"),
                    "prior_private_sale_carryforward_eur": Decimal("0.00"),
                    "updated_private_sale_carryforward_eur": Decimal("0.00"),
                }),
                mock.patch.object(germany_model, "load_dher_results", return_value={"total_gain_eur": Decimal("0.00")}),
                mock.patch.object(germany_model, "load_fund_classification", return_value={}),
                mock.patch.object(germany_model, "compute_germany_vanilla_checkpoint_2025", return_value=self._vanilla_checkpoint_for_germany_main()),
                self.assertRaisesRegex(ValueError, "§ 23|private-sale"),
            ):
                germany_model.main()

    def test_elster_renderer_uses_germany_model_projection_not_raw_capital_inputs(self) -> None:
        # Render surfaces must consume the final Germany core output. If the raw normalized
        # capital files move after germany_model has produced its § 20/§ 32d/§ 36 projection,
        # the renderer should still be able to render that frozen projection instead of
        # rebuilding legal buckets from raw CSVs.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            env = os.environ.copy()
            env.update(
                {
                    "TAX_PROJECT_ROOT": str(root),
                    "TAX_YEAR": "2025",
                    "TAX_WORKSPACE_ROOT": str(root / "years" / "2025"),
                    "TAX_USE_YEAR_LAYOUT": "1",
                }
            )
            # F-A4: Pipeline 1 (run_derivation) writes derived-facts.json
            # which Pipeline 2 (germany_model) reads at the boundary.
            # Subprocess tests must chain them explicitly because
            # run_year is not orchestrating here.
            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.run_derivation"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )
            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.germany_model"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )
            (paths.derived_facts_root / "germany" / "income-cashflows.csv").unlink()
            (paths.derived_facts_root / "germany" / "capital-sales-detail.csv").unlink()

            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.germany_elster_entry_sheet"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )

            kap_summary = paths.analysis_root / "germany-kap-summary.csv"
            entry_sheet = paths.analysis_root / "germany-elster-entry-sheet.md"
            self.assertTrue(kap_summary.exists())
            self.assertIn("Capital Audit Notes", entry_sheet.read_text())

    def test_elster_entry_sheet_renders_integrated_bank_certificate_projection_only(self) -> None:
        # § 20/§ 32d/§ 36 bank certificate handling happens in the Germany core.
        # The ELSTER renderer must consume the frozen projection and must not reject
        # or recompute raw sidecar-shaped inputs.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
            inputs = {
                "foreign_tax_1099_eur": Decimal("0.00"),
                "person_2_bank_certificate_kap_income_eur": Decimal("0.00"),
                "person_2_bank_certificate_kap_stock_gain_eur": Decimal("0.00"),
                "person_2_bank_certificate_sparer_pauschbetrag_used_eur": Decimal("0.00"),
                "person_2_bank_certificate_foreign_tax_credit_eur": Decimal("0.00"),
                "person_2_bank_certificate_kest_withheld_eur": Decimal("10.01"),
                "person_2_bank_certificate_soli_withheld_eur": Decimal("0.01"),
            }
            results = root / "germany-model-results.json"
            results.write_text(
                json.dumps(
                    {
                        "render_projection": {
                            "elster": {
                                "kap_summary_rows": [
                                    ["KAP2", "37", "10.01", "Integrated typed certificate withholding."],
                                    ["KAP2", "38", "0.01", "Integrated typed certificate soli."],
                                ],
                                "kap_inv_fund_rows": [],
                                "n_breakdown_rows": [],
                                "capital_audit": {},
                            }
                        }
                    }
                )
            )
            kap_summary = root / "kap-summary.csv"
            with (
                mock.patch.object(germany_elster_entry_sheet, "YEAR_PATHS", paths),
                mock.patch.object(germany_elster_entry_sheet, "RESULTS_JSON", results),
                mock.patch.object(germany_elster_entry_sheet, "STRUCTURED_INPUTS", {
                    "germany_income_cashflows": paths.derived_facts_root / "germany" / "income-cashflows.csv",
                    "germany_capital_sales_detail": paths.derived_facts_root / "germany" / "capital-sales-detail.csv",
                }),
                mock.patch.object(germany_elster_entry_sheet, "STEPS", paths.analysis_root),
                mock.patch.object(germany_elster_entry_sheet, "KAP_SUMMARY_CSV", kap_summary),
                mock.patch.object(germany_elster_entry_sheet, "KAP_INV_FUND_CSV", root / "kap-inv.csv"),
                mock.patch.object(germany_elster_entry_sheet, "N_BREAKDOWN_CSV", root / "n.csv"),
                mock.patch.object(germany_elster_entry_sheet, "load_german_person_slots", return_value=[
                    {"slot": "person_1", "order_label": "Person 1", "anlage_n_label": "N1", "anlage_kap_label": "KAP1"},
                    {"slot": "person_2", "order_label": "Person 2", "anlage_n_label": "N2", "anlage_kap_label": "KAP2"},
                ]),
                mock.patch.object(germany_elster_entry_sheet, "load_manual_overrides", return_value={"fund_classification": {"fund_types": {"VTI": "aktienfonds"}}}),
                mock.patch.object(germany_elster_entry_sheet, "load_fund_classification", return_value={"VTI": "aktienfonds"}),
                mock.patch.object(germany_elster_entry_sheet, "load_joint_ordinary_inputs_2025", return_value=SimpleNamespace()),
                mock.patch.object(germany_elster_entry_sheet, "compute_joint_ordinary_assessment_2025", return_value=self._ordinary_assessment_for_germany_main()),
            ):
                germany_elster_entry_sheet.aggregate(inputs)

            self.assertIn("KAP2,37,10.01", kap_summary.read_text())


class GermanyCsvStatutoryConstantsAssertionTest(unittest.TestCase):
    """F-DE-1 / Invariant I1: workspace de-tax-constants.csv rows that
    duplicate centralized 2025 statutory constants must equal those
    constants. Drift fails closed at load time so a workspace edit cannot
    silently override Bundesrecht.

    Authority:
    - § 32d Abs. 1 Satz 1 EStG (25% Abgeltungsteuer):
      https://www.gesetze-im-internet.de/estg/__32d.html
    - § 20 Abs. 9 Sätze 1 und 2 EStG (€2,000 / €1,000 Sparer-Pauschbetrag):
      https://www.gesetze-im-internet.de/estg/__20.html
    - § 22 Nr. 3 Satz 2 EStG (€256 Freigrenze):
      https://www.gesetze-im-internet.de/estg/__22.html
    - § 4 Satz 1 SolzG 1995 (5,5% Solidaritätszuschlag):
      https://www.gesetze-im-internet.de/solzg_1995/__4.html
    """

    def test_canonical_values_pass(self) -> None:
        from tax_pipeline.y2025.germany_law import (
            assert_germany_csv_statutory_constants_2025,
        )

        # The four centralized statutory values must validate cleanly.
        assert_germany_csv_statutory_constants_2025(
            {
                "capital_tax_rate": Decimal("0.25"),
                "saver_allowance_eur": Decimal("2000.00"),
                "soli_rate": Decimal("0.055"),
                "other_income_22nr3_freigrenze_eur": Decimal("256.00"),
            }
        )

    def test_drifted_capital_tax_rate_fails_closed(self) -> None:
        from tax_pipeline.y2025.germany_law import (
            assert_germany_csv_statutory_constants_2025,
        )

        with self.assertRaises(ValueError) as raised:
            assert_germany_csv_statutory_constants_2025(
                {"capital_tax_rate": Decimal("0.20")}
            )
        # The error must name the offending key, the drift, and a § 32d
        # citation so a human reviewer can locate the workspace edit.
        self.assertIn("capital_tax_rate", str(raised.exception))
        self.assertIn("32d", str(raised.exception))

    def test_drifted_soli_rate_fails_closed(self) -> None:
        from tax_pipeline.y2025.germany_law import (
            assert_germany_csv_statutory_constants_2025,
        )

        with self.assertRaises(ValueError) as raised:
            assert_germany_csv_statutory_constants_2025(
                {"soli_rate": Decimal("0.06")}
            )
        self.assertIn("soli_rate", str(raised.exception))
        self.assertIn("SolzG", str(raised.exception))

    def test_drifted_saver_allowance_fails_closed(self) -> None:
        from tax_pipeline.y2025.germany_law import (
            assert_germany_csv_statutory_constants_2025,
        )

        with self.assertRaises(ValueError) as raised:
            assert_germany_csv_statutory_constants_2025(
                {"saver_allowance_eur": Decimal("1500.00")}
            )
        self.assertIn("saver_allowance_eur", str(raised.exception))
        self.assertIn("§ 20 Abs. 9", str(raised.exception))

    def test_drifted_freigrenze_fails_closed(self) -> None:
        from tax_pipeline.y2025.germany_law import (
            assert_germany_csv_statutory_constants_2025,
        )

        with self.assertRaises(ValueError) as raised:
            assert_germany_csv_statutory_constants_2025(
                {"other_income_22nr3_freigrenze_eur": Decimal("300.00")}
            )
        self.assertIn("other_income_22nr3_freigrenze_eur", str(raised.exception))
        self.assertIn("§ 22 Nr. 3", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
