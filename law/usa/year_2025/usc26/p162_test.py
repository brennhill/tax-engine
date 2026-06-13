"""§ 61 / § 162 Schedule C net-profit + § 199A QBI-gate tests.

Authority:
- 26 U.S.C. § 61 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61)
- 26 U.S.C. § 162 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162)
- 26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c)
  (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A)
- IRS Schedule C (Form 1040), IRS-VERIFIED 2026-06-13 against
  https://www.irs.gov/pub/irs-pdf/f1040sc.pdf (line 7 gross income,
  line 28 total expenses, line 31 net profit).

Asserts identity with ``tax_pipeline.y2025.us_law`` and concrete numeric
outcomes (CLAUDE.md: tests cite the same authority and assert numbers).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p162 import (
    BUSINESS_INCOME_SOURCE_FOREIGN,
    BUSINESS_INCOME_SOURCE_US_EFFECTIVELY_CONNECTED,
    USC_162_URL,
    USC_199A_URL,
    USC_61_URL,
    USQBIGateAssessment2025,
    USScheduleCInputs2025,
    qbi_gate_2025,
    schedule_c_net_profit_2025,
)
from tax_pipeline.y2025.us_law import (
    USC_162_URL as ORIG_162,
    USC_199A_URL as ORIG_199A,
    USC_61_URL as ORIG_61,
    USScheduleCInputs2025 as ORIG_INPUTS,
    qbi_gate_2025 as orig_qbi_gate,
    schedule_c_net_profit_2025 as orig_net_profit,
)


def _sc(receipts: str, expenses: str, source: str = BUSINESS_INCOME_SOURCE_FOREIGN):
    return USScheduleCInputs2025(
        gross_receipts_usd=Decimal(receipts),
        business_expenses_usd=Decimal(expenses),
        business_income_source=source,
    )


class P162IdentityTest(unittest.TestCase):
    def test_urls_match_production(self) -> None:
        self.assertEqual(USC_61_URL, ORIG_61)
        self.assertEqual(USC_162_URL, ORIG_162)
        self.assertEqual(USC_199A_URL, ORIG_199A)

    def test_net_profit_matches_production(self) -> None:
        inputs = _sc("120000.00", "30000.00")
        self.assertEqual(
            schedule_c_net_profit_2025(inputs=inputs),
            orig_net_profit(inputs=ORIG_INPUTS(
                gross_receipts_usd=Decimal("120000.00"),
                business_expenses_usd=Decimal("30000.00"),
                business_income_source=BUSINESS_INCOME_SOURCE_FOREIGN,
            )),
        )

    def test_qbi_gate_matches_production(self) -> None:
        inputs = _sc("120000.00", "30000.00")
        self.assertEqual(
            qbi_gate_2025(schedule_c_inputs=inputs),
            orig_qbi_gate(schedule_c_inputs=ORIG_INPUTS(
                gross_receipts_usd=Decimal("120000.00"),
                business_expenses_usd=Decimal("30000.00"),
                business_income_source=BUSINESS_INCOME_SOURCE_FOREIGN,
            )),
        )


class P162HandDerivedStatuteTest(unittest.TestCase):
    """Hand-computed § 61 / § 162 netting from Schedule C line 31 =
    line 7 − line 28, independent of the production module.
    """

    def test_net_profit_120k_receipts_30k_expenses(self) -> None:
        # § 61(a)(2) gross income (Schedule C line 7) $120,000 − § 162(a)
        # expenses (line 28) $30,000 = net profit (line 31) $90,000.
        out = schedule_c_net_profit_2025(inputs=_sc("120000.00", "30000.00"))
        self.assertEqual(out.net_profit_usd, Decimal("90000.00"))
        self.assertEqual(out.gross_receipts_usd, Decimal("120000.00"))
        self.assertEqual(out.business_expenses_usd, Decimal("30000.00"))

    def test_loss_is_not_floored(self) -> None:
        # A Schedule C loss is carried through signed (not floored at zero
        # on Schedule C): receipts $10,000 − expenses $14,500 = −$4,500.
        out = schedule_c_net_profit_2025(inputs=_sc("10000.00", "14500.00"))
        self.assertEqual(out.net_profit_usd, Decimal("-4500.00"))

    def test_zero_facts_yields_zero_profit(self) -> None:
        out = schedule_c_net_profit_2025(inputs=_sc("0.00", "0.00"))
        self.assertEqual(out.net_profit_usd, Decimal("0.00"))

    def test_negative_receipts_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            schedule_c_net_profit_2025(inputs=_sc("-1.00", "0.00"))


class P199AQBIGateTest(unittest.TestCase):
    """26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c): foreign-source business
    income is NOT QBI → the deduction is not_applicable (zero), never a
    granted 20 % deduction.
    """

    def test_foreign_source_grants_zero_qbi(self) -> None:
        gate = qbi_gate_2025(schedule_c_inputs=_sc("120000.00", "30000.00"))
        self.assertIsInstance(gate, USQBIGateAssessment2025)
        self.assertEqual(gate.status, "not_applicable")
        self.assertFalse(gate.applicable)
        self.assertEqual(gate.qbi_deduction_usd, Decimal("0.00"))
        self.assertEqual(gate.business_income_source, BUSINESS_INCOME_SOURCE_FOREIGN)
        self.assertIn("§ 199A(c)(3)(A)(i)", gate.basis)
        self.assertIn("§ 864(c)", gate.basis)

    def test_no_business_income_grants_zero_qbi(self) -> None:
        # A pure wage earner (no Schedule C) has no QBI either.
        gate = qbi_gate_2025(schedule_c_inputs=None)
        self.assertEqual(gate.status, "not_applicable")
        self.assertEqual(gate.qbi_deduction_usd, Decimal("0.00"))

    def test_us_effectively_connected_fails_closed(self) -> None:
        # The QBI-granting path (US-effectively-connected) is not modeled —
        # the engine fails closed rather than granting an unverified 20 %
        # deduction (a LEAK-class over-deduction).
        with self.assertRaises(NotImplementedError):
            qbi_gate_2025(
                schedule_c_inputs=_sc(
                    "120000.00",
                    "30000.00",
                    BUSINESS_INCOME_SOURCE_US_EFFECTIVELY_CONNECTED,
                )
            )


if __name__ == "__main__":
    unittest.main()
