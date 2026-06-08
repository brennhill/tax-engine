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
