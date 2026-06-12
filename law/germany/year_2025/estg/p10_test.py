"""§ 10 EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 10 EStG (https://www.gesetze-im-internet.de/estg/__10.html).
Identity tests assert each public symbol equals the production module.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p10 import (
    OTHER_VORSORGE_CAP_EMPLOYEE_EUR,
    OTHER_VORSORGE_CAP_GENERAL_EUR,
    RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR,
    RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025,
    RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR,
    SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR,
    SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR,
    STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE,
    deductible_basic_health_contribution_2025,
    joint_other_vorsorge_allowed_employee_2025,
    joint_retirement_special_expense_deductions_2025,
    other_vorsorge_allowed_employee_2025,
    retirement_special_expense_deduction_2025,
)
from tax_pipeline.y2025.germany_law import (
    OTHER_VORSORGE_CAP_EMPLOYEE_EUR as PROD_OTHER_VORSORGE_CAP_EMPLOYEE,
    OTHER_VORSORGE_CAP_GENERAL_EUR as PROD_OTHER_VORSORGE_CAP_GENERAL,
    RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR as PROD_BBG,
    RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025 as PROD_BEITRAGSSATZ,
    RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR as PROD_RETIREMENT_CAP,
    SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR as PROD_SA_PAUSCH_JOINT,
    SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR as PROD_SA_PAUSCH_SINGLE,
    STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE as PROD_HEALTH_REDUCTION,
    deductible_basic_health_contribution_2025 as prod_health,
    joint_other_vorsorge_allowed_employee_2025 as prod_joint_other,
    joint_retirement_special_expense_deductions_2025 as prod_joint_retirement,
    other_vorsorge_allowed_employee_2025 as prod_other_employee,
    retirement_special_expense_deduction_2025 as prod_retirement,
)


class P10EstgConstantIdentityTest(unittest.TestCase):
    def test_other_vorsorge_employee_cap_matches(self) -> None:
        self.assertEqual(
            OTHER_VORSORGE_CAP_EMPLOYEE_EUR, PROD_OTHER_VORSORGE_CAP_EMPLOYEE
        )

    def test_other_vorsorge_general_cap_matches(self) -> None:
        self.assertEqual(
            OTHER_VORSORGE_CAP_GENERAL_EUR, PROD_OTHER_VORSORGE_CAP_GENERAL
        )

    def test_retirement_cap_single_matches(self) -> None:
        self.assertEqual(RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR, PROD_RETIREMENT_CAP)

    def test_retirement_bbg_matches(self) -> None:
        self.assertEqual(RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR, PROD_BBG)

    def test_retirement_beitragssatz_matches(self) -> None:
        self.assertEqual(RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025, PROD_BEITRAGSSATZ)

    def test_sonderausgaben_pauschbetrag_single_matches(self) -> None:
        self.assertEqual(SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR, PROD_SA_PAUSCH_SINGLE)

    def test_sonderausgaben_pauschbetrag_joint_matches(self) -> None:
        self.assertEqual(SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR, PROD_SA_PAUSCH_JOINT)

    def test_health_sick_pay_reduction_rate_matches(self) -> None:
        self.assertEqual(STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE, PROD_HEALTH_REDUCTION)


class P10EstgFunctionIdentityTest(unittest.TestCase):
    def test_retirement_single_matches_production(self) -> None:
        emp = Decimal("12000.00")
        empr = Decimal("12000.00")
        self.assertEqual(
            retirement_special_expense_deduction_2025(emp, empr),
            prod_retirement(emp, empr),
        )

    def test_retirement_capped_matches_production(self) -> None:
        # Combined exceeds €29,344 cap.
        emp = Decimal("20000.00")
        empr = Decimal("15000.00")
        self.assertEqual(
            retirement_special_expense_deduction_2025(emp, empr),
            prod_retirement(emp, empr),
        )

    def test_basic_health_matches_production(self) -> None:
        h = Decimal("4000.00")
        n = Decimal("500.00")
        rate = Decimal("0.04")
        self.assertEqual(
            deductible_basic_health_contribution_2025(
                h, n, statutory_health_sick_pay_reduction_rate=rate
            ),
            prod_health(h, n, statutory_health_sick_pay_reduction_rate=rate),
        )

    def test_other_vorsorge_employee_matches_production(self) -> None:
        # health/nursing fully consume the cap → other = 0
        result_shadow = other_vorsorge_allowed_employee_2025(
            Decimal("4500.00"), Decimal("700.00")
        )
        result_prod = prod_other_employee(Decimal("4500.00"), Decimal("700.00"))
        self.assertEqual(result_shadow, result_prod)
        # health/nursing under cap → some headroom
        result_shadow = other_vorsorge_allowed_employee_2025(
            Decimal("1000.00"), Decimal("500.00")
        )
        result_prod = prod_other_employee(Decimal("1000.00"), Decimal("500.00"))
        self.assertEqual(result_shadow, result_prod)


class P10EstgSelfEmployedStatuteTest(unittest.TestCase):
    """Self-employed (Freiberufler) § 10 EStG cases.

    A pure freelancer funds their own Vorsorge out of pocket: there is no
    employer pension share (§ 3 Nr. 62 EStG share = €0), so the existing
    § 10 functions apply unchanged with the employer argument fixed at €0.
    Verified against gesetze-im-internet.de:
    - § 10 Abs. 3 Satz 6 EStG: Altersvorsorge 100% deductible from 2023,
      up to the €29,344 Höchstbetrag.
    - § 10 Abs. 1 Nr. 3 EStG: base Kranken-/Pflegeversicherung fully
      deductible; § 10 Abs. 1 Nr. 3 Satz 4: 4% Krankengeld reduction
      applies ONLY where a Krankengeld-Anspruch can arise — a freelancer
      with no entitlement uses a 0% reduction.
    - § 10 Abs. 4 Satz 1/2 EStG: a self-employed person who funds their own
      KV takes the €2,800 cap (Satz 1 general cap), NOT the €1,900 Satz 2
      reduced cap (which is for taxpayers covered without own expense).
    https://www.gesetze-im-internet.de/estg/__10.html
    """

    def test_se_altersvorsorge_below_cap_fully_deductible(self) -> None:
        # § 10 Abs. 1 Nr. 2 / Abs. 3 Satz 6 EStG: freelancer pays €12,000
        # Basisrente, employer share €0 → 100% deductible, under €29,344 cap.
        self.assertEqual(
            retirement_special_expense_deduction_2025(
                Decimal("12000.00"), Decimal("0.00")
            ),
            Decimal("12000.00"),
        )

    def test_se_altersvorsorge_above_cap_is_capped(self) -> None:
        # § 10 Abs. 3 Satz 1 EStG: freelancer pays €35,000, employer €0 →
        # capped at the €29,344 single Höchstbetrag.
        self.assertEqual(
            retirement_special_expense_deduction_2025(
                Decimal("35000.00"), Decimal("0.00")
            ),
            RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR,
        )
        self.assertEqual(
            retirement_special_expense_deduction_2025(
                Decimal("35000.00"), Decimal("0.00")
            ),
            Decimal("29344.00"),
        )

    def test_se_altersvorsorge_at_cap_exactly(self) -> None:
        # § 10 Abs. 3 Satz 1 EStG: exactly €29,344 → fully deductible.
        self.assertEqual(
            retirement_special_expense_deduction_2025(
                Decimal("29344.00"), Decimal("0.00")
            ),
            Decimal("29344.00"),
        )

    def test_se_base_kv_pv_fully_deductible_no_krankengeld(self) -> None:
        # § 10 Abs. 1 Nr. 3 EStG: freelancer base KV €5,000 + PV €1,000
        # with NO Krankengeld entitlement (0% reduction per Satz 4) →
        # €6,000 fully deductible (Nr. 3 is NOT subject to the Abs. 4 cap).
        self.assertEqual(
            deductible_basic_health_contribution_2025(
                Decimal("5000.00"),
                Decimal("1000.00"),
                statutory_health_sick_pay_reduction_rate=Decimal("0.00"),
            ),
            Decimal("6000.00"),
        )

    def test_se_base_kv_pv_with_krankengeld_reduction(self) -> None:
        # § 10 Abs. 1 Nr. 3 Satz 4 EStG: freelancer voluntarily insured WITH
        # Krankengeld entitlement → 4% reduction on KV only.
        # 5000 × 0.96 + 1000 = 4800 + 1000 = 5800.
        self.assertEqual(
            deductible_basic_health_contribution_2025(
                Decimal("5000.00"),
                Decimal("1000.00"),
                statutory_health_sick_pay_reduction_rate=STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE,
            ),
            Decimal("5800.00"),
        )

    def test_se_sonstige_binds_at_2800_not_1900(self) -> None:
        # § 10 Abs. 4 Satz 1 EStG: a self-employed person who funds their own
        # KV takes the €2,800 cap. With no health/nursing consuming the cap
        # and €5,000 sonstige, the deduction binds at €2,800 (not €1,900).
        allowed_se = other_vorsorge_allowed_employee_2025(
            Decimal("0.00"),
            Decimal("5000.00"),
            cap_eur=OTHER_VORSORGE_CAP_GENERAL_EUR,
        )
        self.assertEqual(allowed_se, Decimal("2800.00"))
        # The €1,900 employee cap would bind lower — proves €2,800 is higher.
        allowed_employee = other_vorsorge_allowed_employee_2025(
            Decimal("0.00"),
            Decimal("5000.00"),
            cap_eur=OTHER_VORSORGE_CAP_EMPLOYEE_EUR,
        )
        self.assertEqual(allowed_employee, Decimal("1900.00"))
        self.assertGreater(allowed_se, allowed_employee)

    def test_se_retirement_joins_joint_combined_base(self) -> None:
        # § 10 Abs. 3 Satz 2 EStG joint: a self-employed spouse's own
        # Altersvorsorge (no employer share) enters the same combined base the
        # joint cap is applied to via se_retirement_contributions.
        from tax_pipeline.y2025.germany_law import (
            PersonOrdinaryInputs2025,
            WageFacts2025,
        )

        def _freelancer(slot: str) -> PersonOrdinaryInputs2025:
            wage = WageFacts2025(
                owner=slot,
                source_files=(),
                gross_wage_eur=Decimal("0.00"),
                withheld_wage_tax_eur=Decimal("0.00"),
                withheld_solidarity_surcharge_eur=Decimal("0.00"),
                multiannual_wage_eur=Decimal("0.00"),
                employer_pension_contribution_eur=Decimal("0.00"),
                employee_pension_contribution_eur=Decimal("0.00"),
                employee_health_insurance_eur=Decimal("0.00"),
                employee_nursing_care_insurance_eur=Decimal("0.00"),
                employee_unemployment_insurance_eur=Decimal("0.00"),
            )
            return PersonOrdinaryInputs2025(
                slot=slot,
                order_label=slot,
                display_name=slot,
                owner=slot,
                wage=wage,
                work_equipment_items=(),
                home_office_days_without_visit=0,
                home_office_days_with_visit=0,
                manual_work_equipment_deduction_eur=Decimal("0.00"),
                telecom_deduction_eur=Decimal("0.00"),
                employment_legal_insurance_deduction_eur=Decimal("0.00"),
                cross_border_tax_help_deduction_eur=Decimal("0.00"),
                health_insurance_sick_pay_reduction_rate=Decimal("0.00"),
                other_vorsorge_cap_eur=OTHER_VORSORGE_CAP_GENERAL_EUR,
            )

        people = (_freelancer("person_1"), _freelancer("person_2"))
        # Wage-only (no SE injection) → €0 joint retirement (the bug).
        self.assertEqual(
            joint_retirement_special_expense_deductions_2025(
                people,
                se_retirement_contributions=(Decimal("0.00"), Decimal("0.00")),
            ),
            (Decimal("0.00"), Decimal("0.00")),
        )
        # SE Altersvorsorge €12,000 + €8,000 (combined €20,000 < €58,688 joint
        # cap) → fully deductible, allocated by own-contribution weight.
        self.assertEqual(
            joint_retirement_special_expense_deductions_2025(
                people,
                se_retirement_contributions=(Decimal("12000.00"), Decimal("8000.00")),
            ),
            (Decimal("12000.00"), Decimal("8000.00")),
        )
        # None defaults to all-zero SE (back-compat with wage-only callers).
        self.assertEqual(
            joint_retirement_special_expense_deductions_2025(people),
            (Decimal("0.00"), Decimal("0.00")),
        )

    def test_se_base_kv_consumes_abs4_cap_before_sonstige(self) -> None:
        # § 10 Abs. 4 EStG: basic health/nursing consume the €2,800 cap first;
        # a freelancer whose base KV/PV (€6,000) exceeds the cap leaves €0
        # room for sonstige. (The Nr. 3 base remains separately deductible via
        # deductible_basic_health_contribution_2025; only the Nr. 3a sonstige
        # is capped here.)
        self.assertEqual(
            other_vorsorge_allowed_employee_2025(
                Decimal("6000.00"),
                Decimal("1200.00"),
                cap_eur=OTHER_VORSORGE_CAP_GENERAL_EUR,
            ),
            Decimal("0.00"),
        )


class P10EstgStatuteTest(unittest.TestCase):
    def test_other_vorsorge_employee_cap_is_1900(self) -> None:
        # § 10 Abs. 4 Satz 1 EStG.
        self.assertEqual(OTHER_VORSORGE_CAP_EMPLOYEE_EUR, Decimal("1900.00"))

    def test_other_vorsorge_general_cap_is_2800(self) -> None:
        # § 10 Abs. 4 Satz 2 EStG.
        self.assertEqual(OTHER_VORSORGE_CAP_GENERAL_EUR, Decimal("2800.00"))

    def test_health_sick_pay_reduction_rate_is_4_percent(self) -> None:
        # § 10 Abs. 1 Nr. 3 Satz 4 EStG.
        self.assertEqual(STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE, Decimal("0.04"))

    def test_retirement_cap_matches_bbg_times_beitragssatz(self) -> None:
        # § 10 Abs. 3 Satz 1 EStG: cap = BBG × Beitragssatz, BMF rounded.
        # €118,800 × 0.247 = €29,343.60 → BMF rounds to €29,344.
        product = (
            RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR
            * RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025
        )
        self.assertEqual(product, Decimal("29343.6000"))
        # BMF rounds to whole euros.
        self.assertEqual(RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR, Decimal("29344.00"))

    def test_sonderausgaben_pauschbetrag_single_is_36(self) -> None:
        # § 10c EStG.
        self.assertEqual(SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR, Decimal("36.00"))

    def test_sonderausgaben_pauschbetrag_joint_is_72(self) -> None:
        # § 10c EStG (joint = 2× single).
        self.assertEqual(SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR, Decimal("72.00"))


if __name__ == "__main__":
    unittest.main()
