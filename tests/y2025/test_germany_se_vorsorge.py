"""DE25-SE-VORSORGE end-to-end — self-employed § 10 EStG Vorsorgeaufwendungen.

A pure freelancer (Freiberufler) funds their own Kranken-/Pflege-/
Rentenversicherung out of pocket. Before this slice the engine read Vorsorge
ONLY from wage facts, so a freelancer got a ZERO § 10 deduction and an
overstated tax. This slice routes the freelancer's own contributions into the
EXISTING § 10 stages (DE25-05 retirement, DE25-06 health/other) so the SAME
§ 10 Abs. 3 / Abs. 4 caps apply over the combined base — no parallel
deduction path.

Authority (verified against gesetze-im-internet.de):
- § 10 Abs. 1 Nr. 2 EStG — Altersvorsorge (Basisrente / RV / Versorgungswerk),
  100% deductible from 2023 (Abs. 3 Satz 6) up to the Abs. 3 Höchstbetrag.
  https://www.gesetze-im-internet.de/estg/__10.html
- § 10 Abs. 1 Nr. 3 EStG — base Kranken- + Pflegeversicherung fully
  deductible; Satz 4: 4% Krankengeld reduction applies ONLY where a
  Krankengeld-Anspruch can arise (a freelancer without entitlement → 0%).
- § 10 Abs. 1 Nr. 3a EStG — sonstige Vorsorge within the Abs. 4 cap.
- § 10 Abs. 4 Satz 1 EStG — €2,800 cap for the self-employed who fund their
  own KV (NOT the €1,900 Satz 2 reduced cap); Satz 3: joint cap = sum of each
  spouse's individual cap.
- § 32a EStG — 2025 tariff (zone-3 polynomial, hand-verified below).

Asserts concrete euro outcomes hand-derivable from the cited law (CLAUDE.md).
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
    BusinessVorsorgeInputs2025,
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    WageFacts2025,
    compute_joint_ordinary_assessment_2025,
    german_income_tax_single_2025,
)

D = Decimal


def _wage(
    owner: str,
    *,
    gross: str = "0.00",
    employee_pension: str = "0.00",
    employer_pension: str = "0.00",
    health: str = "0.00",
    nursing: str = "0.00",
    unemployment: str = "0.00",
) -> WageFacts2025:
    return WageFacts2025(
        owner=owner,
        source_files=("synthetic.pdf",),
        gross_wage_eur=D(gross),
        withheld_wage_tax_eur=D("0.00"),
        withheld_solidarity_surcharge_eur=D("0.00"),
        multiannual_wage_eur=D("0.00"),
        employer_pension_contribution_eur=D(employer_pension),
        employee_pension_contribution_eur=D(employee_pension),
        employee_health_insurance_eur=D(health),
        employee_nursing_care_insurance_eur=D(nursing),
        employee_unemployment_insurance_eur=D(unemployment),
    )


def _person(
    slot: str,
    *,
    wage: WageFacts2025,
    cap: str = "2800.00",
    sick_pay_rate: str = "0.00",
) -> PersonOrdinaryInputs2025:
    return PersonOrdinaryInputs2025(
        slot=slot,
        order_label=slot.replace("_", " ").title(),
        display_name=slot.replace("_", " ").title(),
        owner=slot,
        wage=wage,
        work_equipment_items=(),
        home_office_days_without_visit=0,
        home_office_days_with_visit=0,
        manual_work_equipment_deduction_eur=D("0.00"),
        telecom_deduction_eur=D("0.00"),
        employment_legal_insurance_deduction_eur=D("0.00"),
        cross_border_tax_help_deduction_eur=D("0.00"),
        health_insurance_sick_pay_reduction_rate=D(sick_pay_rate),
        other_vorsorge_cap_eur=D(cap),
    )


def _se_vorsorge(
    slot: str,
    *,
    retirement: str = "0.00",
    basic_health: str = "0.00",
    nursing: str = "0.00",
    other: str = "0.00",
) -> BusinessVorsorgeInputs2025:
    return BusinessVorsorgeInputs2025(
        slot=slot,
        retirement_contributions_eur=D(retirement),
        basic_health_contributions_eur=D(basic_health),
        nursing_care_contributions_eur=D(nursing),
        other_vorsorge_contributions_eur=D(other),
    )


# § 4 Abs. 3 profit 61,750 (receipts 80,000 − expenses 18,250).
_FREELANCER_BUSINESS = BusinessIncomeInputs2025(
    operating_receipts_eur=D("80000.00"),
    operating_expenses_eur=D("18250.00"),
)


class PureFreelancerVorsorgeTest(unittest.TestCase):
    """A pure Freiberufler: profit only, all Vorsorge self-funded."""

    def _assessment(self, business_vorsorge):
        person = _person("person_1", wage=_wage("person_1"), cap="2800.00")
        inputs = JointOrdinaryInputs2025(
            people=(person,),
            other_income_22nr3_eur=D("0.00"),
            other_income_22nr3_threshold_eur=D("256.00"),
            prepayments_eur=D("0.00"),
            business_income=_FREELANCER_BUSINESS,
            business_vorsorge=business_vorsorge,
        )
        return compute_joint_ordinary_assessment_2025(inputs)

    def test_freelancer_section_10_total_and_taxable_income(self) -> None:
        # Fixture (spec § 8): profit 61,750; Altersvorsorge 12,000, KV 5,000,
        # PV 1,000, sonstige 1,200; no Krankengeld (0% reduction).
        #
        # § 10 Abs. 1 Nr. 2: retirement = min(12,000, 29,344) − 0 = 12,000.
        # § 10 Abs. 1 Nr. 3: basic = 5,000×(1−0) + 1,000 = 6,000.
        # § 10 Abs. 1 Nr. 3a / Abs. 4: the €2,800 cap is consumed in full by
        #   the 6,000 basic KV/PV, so sonstige allowed = 0 (1,200 crowded out).
        # § 10 deduction = 12,000 + 6,000 + 0 = 18,000.
        # total_special_expenses = 18,000 + 36 (§ 10c) = 18,036.
        # zvE = 61,750 − 18,036 = 43,714.
        assessment = self._assessment(
            (
                _se_vorsorge(
                    "person_1",
                    retirement="12000.00",
                    basic_health="5000.00",
                    nursing="1000.00",
                    other="1200.00",
                ),
            )
        )
        person = assessment.people[0]
        self.assertEqual(person.retirement_contributions_eur, D("12000.00"))
        self.assertEqual(person.health_and_nursing_contributions_eur, D("6000.00"))
        self.assertEqual(assessment.total_special_expenses_eur, D("18036.00"))
        self.assertEqual(assessment.joint_taxable_income_eur, D("43714.00"))

    def test_freelancer_tariff_is_materially_lower_than_zero_vorsorge(self) -> None:
        # The bug being fixed: without the Vorsorge route, zvE = 61,750 − 36 =
        # 61,714 and § 32a tax = 15,088. With the route, zvE = 43,714 and tax
        # = 8,531 — a €6,557 reduction the freelancer is legally entitled to.
        with_vorsorge = self._assessment(
            (
                _se_vorsorge(
                    "person_1",
                    retirement="12000.00",
                    basic_health="5000.00",
                    nursing="1000.00",
                    other="1200.00",
                ),
            )
        )
        zero_vorsorge = self._assessment(())  # declared, but all zero
        self.assertEqual(zero_vorsorge.joint_taxable_income_eur, D("61714.00"))
        self.assertEqual(with_vorsorge.joint_income_tax_eur, german_income_tax_single_2025(D("43714.00")))
        self.assertEqual(with_vorsorge.joint_income_tax_eur, D("8531"))
        self.assertEqual(zero_vorsorge.joint_income_tax_eur, D("15088"))
        self.assertLess(
            with_vorsorge.joint_income_tax_eur, zero_vorsorge.joint_income_tax_eur
        )
        self.assertEqual(
            zero_vorsorge.joint_income_tax_eur - with_vorsorge.joint_income_tax_eur,
            D("6557"),
        )

    def test_freelancer_altersvorsorge_capped_at_29344(self) -> None:
        # § 10 Abs. 3 Satz 1: Altersvorsorge 35,000 → capped at 29,344.
        assessment = self._assessment(
            (_se_vorsorge("person_1", retirement="35000.00"),)
        )
        self.assertEqual(
            assessment.people[0].retirement_contributions_eur, D("29344.00")
        )

    def test_freelancer_sonstige_uses_2800_cap_when_room_remains(self) -> None:
        # § 10 Abs. 4 Satz 1: with NO basic KV/PV consuming the cap, €5,000
        # sonstige binds at the €2,800 self-employed cap (not €1,900).
        assessment = self._assessment(
            (_se_vorsorge("person_1", other="5000.00"),)
        )
        person = assessment.people[0]
        self.assertEqual(person.health_and_nursing_contributions_eur, D("0.00"))
        self.assertEqual(person.other_vorsorge_allowed_eur, D("2800.00"))


class BothWorkerSingleCombinedCapTest(unittest.TestCase):
    """``both`` worker: wage + self-employed Vorsorge under ONE § 10 cap."""

    def test_combined_retirement_cap_applied_once(self) -> None:
        # § 10 Abs. 3: wage employee_pension 15,000 (employer 5,000) + SE
        # retirement 20,000. Combined own base for the single cap:
        #   gross base = (15,000 + 20,000) + 5,000 employer = 40,000
        #   capped at 29,344; deductible = 29,344 − 5,000 employer = 24,344.
        # The cap is applied ONCE over the combined base, not twice.
        wage = _wage(
            "person_1",
            gross="40000.00",
            employee_pension="15000.00",
            employer_pension="5000.00",
        )
        person = _person("person_1", wage=wage, cap="2800.00")
        inputs = JointOrdinaryInputs2025(
            people=(person,),
            other_income_22nr3_eur=D("0.00"),
            other_income_22nr3_threshold_eur=D("256.00"),
            prepayments_eur=D("0.00"),
            business_income=_FREELANCER_BUSINESS,
            business_vorsorge=(_se_vorsorge("person_1", retirement="20000.00"),),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(
            assessment.people[0].retirement_contributions_eur, D("24344.00")
        )

    def test_combined_health_base_flows_through_one_cap(self) -> None:
        # § 10 Abs. 1 Nr. 3 / Abs. 4: wage KV 3,000 (4% reduction) + SE KV
        # 2,000 (own, 0% — but the per-person rate is one field, 0.04 here for
        # the wage Krankengeld) and wage unemployment 1,000 + SE other 1,000.
        #   basic = (3,000 + 2,000)×0.96 + 0 nursing = 4,800.
        #   other base = 1,000 + 1,000 = 2,000; cap 2,800 fully consumed by
        #   the 4,800 basic → other allowed = 0.
        wage = _wage(
            "person_1",
            gross="40000.00",
            health="3000.00",
            unemployment="1000.00",
        )
        person = _person("person_1", wage=wage, cap="2800.00", sick_pay_rate="0.04")
        inputs = JointOrdinaryInputs2025(
            people=(person,),
            other_income_22nr3_eur=D("0.00"),
            other_income_22nr3_threshold_eur=D("256.00"),
            prepayments_eur=D("0.00"),
            business_income=_FREELANCER_BUSINESS,
            business_vorsorge=(
                _se_vorsorge("person_1", basic_health="2000.00", other="1000.00"),
            ),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        self.assertEqual(
            assessment.people[0].health_and_nursing_contributions_eur, D("4800.00")
        )


class JointReturnOneSelfEmployedSpouseTest(unittest.TestCase):
    """§ 10 Abs. 3 Satz 2 / Abs. 4 Satz 3: joint caps over both spouses."""

    def _joint_assessment(self):
        # Spouse A: self-employed (cap 2,800), SE retirement 12,000, SE other
        # 1,500, no basic KV/PV so the sonstige cap has room.
        # Spouse B: employee (cap 1,900), wage employee_pension 8,000 (employer
        # 8,000), wage unemployment 800.
        spouse_a = _person(
            "person_1", wage=_wage("person_1"), cap="2800.00", sick_pay_rate="0.00"
        )
        spouse_b = _person(
            "person_2",
            wage=_wage(
                "person_2",
                gross="50000.00",
                employee_pension="8000.00",
                employer_pension="8000.00",
                unemployment="800.00",
            ),
            cap="1900.00",
            sick_pay_rate="0.04",
        )
        inputs = JointOrdinaryInputs2025(
            people=(spouse_a, spouse_b),
            other_income_22nr3_eur=D("0.00"),
            other_income_22nr3_threshold_eur=D("256.00"),
            prepayments_eur=D("0.00"),
            filing_posture="married_joint",
            joint_assessment_prerequisites_validated=True,
            business_income=_FREELANCER_BUSINESS,
            business_vorsorge=(
                _se_vorsorge("person_1", retirement="12000.00", other="1500.00"),
            ),
        )
        return compute_joint_ordinary_assessment_2025(inputs)

    def test_joint_retirement_combines_se_and_wage_under_doubled_cap(self) -> None:
        # § 10 Abs. 3 Satz 2: joint cap = 2 × 29,344 = 58,688.
        # Combined own base = SE 12,000 (A) + wage employee 8,000 (B) = 20,000;
        # gross base + employer 8,000 = 28,000 < 58,688, so deductible =
        # 28,000 − 8,000 employer = 20,000, allocated by own-contribution
        # weight (12,000 : 8,000).
        assessment = self._joint_assessment()
        retirement_total = sum(
            (p.retirement_contributions_eur for p in assessment.people), D("0.00")
        )
        self.assertEqual(retirement_total, D("20000.00"))

    def test_joint_other_vorsorge_uses_summed_2800_plus_1900_cap(self) -> None:
        # § 10 Abs. 4 Satz 3: joint sonstige cap = 2,800 + 1,900 = 4,700.
        # No basic KV/PV consumes it; total sonstige = SE 1,500 (A) + wage
        # unemployment 800×... (B's unemployment 800 enters as Nr. 3a) = 2,300,
        # under the 4,700 joint cap → fully allowed (2,300).
        assessment = self._joint_assessment()
        other_allowed_total = sum(
            (p.other_vorsorge_allowed_eur for p in assessment.people),
            D("0.00"),
        )
        self.assertEqual(other_allowed_total, D("2300.00"))


class SeVorsorgeLoaderFailClosedTest(unittest.TestCase):
    """Loader contracts (CLAUDE.md fail-closed; the headline fix)."""

    def _demo_with_elections(self, tmp: str, **elections):
        paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
        profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
        profile.setdefault("elections", {}).update(elections)
        paths.profile_path.write_text(json.dumps(profile), encoding="utf-8")
        return paths

    def _write_business_income(self, paths) -> None:
        (paths.config_root / "business-income.csv").write_text(
            "key,amount_eur,source,note\n"
            "operating_receipts_eur,80000.00,test,\n"
            "operating_expenses_eur,18250.00,test,\n",
            encoding="utf-8",
        )

    def test_self_employed_without_vorsorge_file_fails_closed(self) -> None:
        # The headline fix: a self-employment posture with no business-vorsorge
        # source must fail closed (never silently understate § 10).
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                de_self_employment_class="freiberuflich_18",
            )
            self._write_business_income(paths)
            with self.assertRaisesRegex(ValueError, "business-vorsorge"):
                load_joint_ordinary_inputs_2025(paths)

    def test_self_employed_loads_declared_vorsorge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                de_self_employment_class="freiberuflich_18",
            )
            self._write_business_income(paths)
            # A freelancer who funds their own KV takes the €2,800 cap.
            people_csv = paths.people_path.read_text(encoding="utf-8")
            people_csv = people_csv.replace(",1900.00,", ",2800.00,")
            paths.people_path.write_text(people_csv, encoding="utf-8")
            (paths.config_root / "business-vorsorge.csv").write_text(
                "slot,key,amount_eur,source,note\n"
                "person_1,retirement,12000.00,test,\n"
                "person_1,basic_health,5000.00,test,\n"
                "person_1,nursing_care,1000.00,test,\n"
                "person_1,other_vorsorge,1200.00,test,\n",
                encoding="utf-8",
            )
            inputs = load_joint_ordinary_inputs_2025(paths)
            self.assertEqual(len(inputs.business_vorsorge), 1)
            bv = inputs.business_vorsorge[0]
            self.assertEqual(bv.slot, "person_1")
            self.assertEqual(bv.retirement_contributions_eur, D("12000.00"))
            self.assertEqual(bv.basic_health_contributions_eur, D("5000.00"))
            self.assertEqual(bv.nursing_care_contributions_eur, D("1000.00"))
            self.assertEqual(bv.other_vorsorge_contributions_eur, D("1200.00"))

    def test_employee_has_no_business_vorsorge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            inputs = load_joint_ordinary_inputs_2025(paths)
            self.assertEqual(inputs.business_vorsorge, ())

    def test_unknown_vorsorge_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                de_self_employment_class="freiberuflich_18",
            )
            self._write_business_income(paths)
            (paths.config_root / "business-vorsorge.csv").write_text(
                "slot,key,amount_eur,source,note\n"
                "person_1,riester_topup,9000.00,test,\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unknown business-vorsorge key"):
                load_joint_ordinary_inputs_2025(paths)

    def test_se_with_1900_cap_and_own_kv_fails_closed(self) -> None:
        # § 10 Abs. 4: a self-employed person funding their own KV must take
        # the €2,800 cap; declaring €1,900 is inconsistent → fail closed.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                de_self_employment_class="freiberuflich_18",
            )
            self._write_business_income(paths)
            # Demo person declares the €1,900 employee cap by default? Force it.
            people_csv = paths.people_path.read_text(encoding="utf-8")
            people_csv = people_csv.replace("2800.00", "1900.00")
            paths.people_path.write_text(people_csv, encoding="utf-8")
            (paths.config_root / "business-vorsorge.csv").write_text(
                "slot,key,amount_eur,source,note\n"
                "person_1,basic_health,5000.00,test,\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"1900|§ 10 Abs. 4"):
                load_joint_ordinary_inputs_2025(paths)

    def test_unknown_slot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                de_self_employment_class="freiberuflich_18",
            )
            self._write_business_income(paths)
            (paths.config_root / "business-vorsorge.csv").write_text(
                "slot,key,amount_eur,source,note\n"
                "person_99,retirement,12000.00,test,\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not a declared person"):
                load_joint_ordinary_inputs_2025(paths)


class DemoInvarianceTest(unittest.TestCase):
    """The wage-earner demo must be value-identical to the pre-slice baseline."""

    def test_wage_earner_vorsorge_and_taxable_income_unchanged(self) -> None:
        # An employee (business_vorsorge=()) yields se_vorsorge_by_slot={} →
        # every § 10 function receives the same wage-derived arguments as
        # before. A wage-only person with no contributions deducts only the
        # § 10c €36 floor → zvE = wage net − 36.
        person = _person("person_1", wage=_wage("person_1", gross="60000.00"))
        inputs = JointOrdinaryInputs2025(
            people=(person,),
            other_income_22nr3_eur=D("0.00"),
            other_income_22nr3_threshold_eur=D("256.00"),
            prepayments_eur=D("0.00"),
        )
        assessment = compute_joint_ordinary_assessment_2025(inputs)
        # § 9a Arbeitnehmer-Pauschbetrag 1,230 → net 58,770; − 36 = 58,734.
        self.assertEqual(assessment.joint_taxable_income_eur, D("58734.00"))
        self.assertEqual(assessment.people[0].retirement_contributions_eur, D("0.00"))
        self.assertEqual(
            assessment.people[0].health_and_nursing_contributions_eur, D("0.00")
        )


if __name__ == "__main__":
    unittest.main()
