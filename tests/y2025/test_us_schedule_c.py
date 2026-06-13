"""US25-SCHEDULE-C end-to-end — 26 U.S.C. § 61 / § 162 Schedule C business
income + § 199A QBI gate (Phase 2 freelancer support).

Authority:
- 26 U.S.C. § 61 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
- 26 U.S.C. § 162 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
- 26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c) —
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A
- 26 U.S.C. § 1401 / § 1402(a)(12) (SE tax) + U.S.-Germany Totalization
  Agreement (1979) — https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
- IRS Schedule C (Form 1040), IRS-VERIFIED 2026-06-13 against
  https://www.irs.gov/pub/irs-pdf/f1040sc.pdf

Exercises the full U.S. rule graph: Schedule C net profit (§ 61 − § 162) →
Schedule 1 line 3 → AGI → § 63 taxable income → § 1 tax, AND the same net
profit as the § 1402(a)(12) SE-tax base, AND the § 199A gate granting ZERO for
foreign-source income, plus the loader fail-closed contracts and demo
invariance. Asserts concrete dollar outcomes hand-derivable from the cited law
(CLAUDE.md: assert numbers, cite authority).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_law import (
    BUSINESS_INCOME_SOURCE_FOREIGN,
    MFS_CAPITAL_LOSS_LIMIT_USD,
    USAssessmentInputs2025,
    USCapitalSourceFacts2025,
    USFTCInputs2025,
    USReturnProfile2025,
    USScheduleCInputs2025,
    USSelfEmploymentInputs2025,
    USTaxConstants2025,
    USTreatyInputs2025,
    compute_us_assessment_2025,
    qbi_gate_2025,
    schedule_c_net_profit_2025,
)
from tax_pipeline.y2025.us_rules import (
    execute_us_rule_graph,
    us_initial_facts_2025,
    us_initial_fingerprints_2025,
)

D = Decimal


def _final_facts(inputs: USAssessmentInputs2025):
    initial = us_initial_facts_2025(inputs)
    execution = execute_us_rule_graph(
        initial, input_fingerprints=us_initial_fingerprints_2025(initial)
    )
    return execution.final_facts


def _single_constants() -> USTaxConstants2025:
    # 2025 single-filer thresholds (the same Rev. Proc. 2024-40 numbers the
    # demo workspace carries). Standard deduction $15,000 (single, 2025).
    return USTaxConstants2025(
        eur_per_usd_yearly_average_2025=D("1.00"),
        standard_deduction_2025_usd=D("15000.00"),
        capital_loss_limit_usd=MFS_CAPITAL_LOSS_LIMIT_USD,
        niit_threshold_usd=D("200000.00"),
        qualified_dividend_zero_rate_ceiling_2025_usd=D("48350.00"),
        qualified_dividend_fifteen_rate_ceiling_2025_usd=D("533400.00"),
        tax_bracket_10_ceiling_2025_usd=D("11925.00"),
        tax_bracket_12_ceiling_2025_usd=D("48475.00"),
        tax_bracket_22_ceiling_2025_usd=D("103350.00"),
        tax_bracket_24_ceiling_2025_usd=D("197300.00"),
        tax_bracket_32_ceiling_2025_usd=D("250525.00"),
        tax_bracket_35_ceiling_2025_usd=D("626350.00"),
    )


def _zero_capital_facts() -> USCapitalSourceFacts2025:
    return USCapitalSourceFacts2025(
        ordinary_dividends_usd=D("0.00"),
        qualified_dividends_usd=D("0.00"),
        capital_gain_distributions_usd=D("0.00"),
        nondividend_distributions_usd=D("0.00"),
        foreign_tax_paid_usd=D("0.00"),
        interest_income_usd=D("0.00"),
        substitute_payments_usd=D("0.00"),
        staking_income_usd=D("0.00"),
        estimated_payment_2025_usd=D("0.00"),
        passive_ftc_carryover_2024_usd=D("0.00"),
        general_ftc_carryover_2024_usd=D("0.00"),
        german_2024_redetermination_paid_2025_eur=D("0.00"),
        schwab_short_box_a_gain_usd=D("0.00"),
        schwab_short_box_b_gain_usd=D("0.00"),
        schwab_long_box_d_gain_usd=D("0.00"),
        schwab_section_1256_total_usd=D("0.00"),
        jpm_short_type_a_gain_usd=D("0.00"),
        coinbase_short_with_basis_proceeds_usd=D("0.00"),
        coinbase_short_with_basis_basis_usd=D("0.00"),
        coinbase_short_unknown_proceeds_usd=D("0.00"),
        coinbase_short_unknown_basis_reconstructed_usd=D("0.00"),
        coinbase_long_with_basis_proceeds_usd=D("0.00"),
        coinbase_long_with_basis_basis_usd=D("0.00"),
    )


def _freelancer_inputs(
    *,
    schedule_c: USScheduleCInputs2025 | None,
    totalization_certificate_present: bool = False,
) -> USAssessmentInputs2025:
    """A single U.S. citizen abroad with NO wages, NO capital, NO foreign tax —
    only the Schedule C business. Derives the SE base from the Schedule C net
    profit the same way the loader does (the rule graph reads se_inputs)."""
    if schedule_c is not None:
        net_profit = schedule_c_net_profit_2025(inputs=schedule_c).net_profit_usd
        se_net_earnings = max(D("0.00"), net_profit)
    else:
        se_net_earnings = D("0.00")
    return USAssessmentInputs2025(
        constants=_single_constants(),
        profile=USReturnProfile2025(
            filing_status_label="Single",
            spouse_name_for_mfs_line="",
            joint_return_spouse_name="",
            joint_return_with_nra_spouse_election=False,
            accrued_basis_ftc=True,
            include_staking_in_niit=False,
        ),
        capital_facts=_zero_capital_facts(),
        ftc_inputs=USFTCInputs2025(
            taxpayer_gross_wages_eur=D("0.00"),
            spouse_gross_wages_eur=D("0.00"),
            joint_wage_side_tax_eur=D("0.00"),
            foreign_source_passive_dividends_usd=D("0.00"),
            foreign_source_qualified_dividends_usd=D("0.00"),
            foreign_source_net_capital_gain_usd=D("0.00"),
            known_positive_short_capital_gain_usd=D("0.00"),
            known_positive_long_capital_gain_usd=D("0.00"),
            conservative_positive_income_only=True,
            allocate_joint_german_tax_by_wage_share=True,
        ),
        treaty_inputs=USTreatyInputs2025(
            use_treaty_resourcing=False,
            us_source_direct_equity_dividends_usd=D("0.00"),
            us_source_equity_fund_dividends_usd=D("0.00"),
            us_source_non_equity_fund_dividends_usd=D("0.00"),
        ),
        se_inputs=USSelfEmploymentInputs2025(
            net_se_earnings_usd=se_net_earnings,
            us_w2_medicare_taxable_wages_usd=D("0.00"),
            totalization_certificate_present=totalization_certificate_present,
        ),
        schedule_c_inputs=schedule_c,
    )


def _sc(receipts: str, expenses: str, source: str = BUSINESS_INCOME_SOURCE_FOREIGN):
    return USScheduleCInputs2025(
        gross_receipts_usd=D(receipts),
        business_expenses_usd=D(expenses),
        business_income_source=source,
    )


class ScheduleCProfitFlowsIntoAGIAndTaxTest(unittest.TestCase):
    """§ 61 / § 162 Schedule C net profit → Schedule 1 line 3 → AGI →
    § 63 taxable income → § 1 regular tax (hand-derived)."""

    def test_net_profit_flows_to_schedule_1_agi_and_taxable_income(self) -> None:
        # § 61(a)(2) gross income $120,000 − § 162(a) expenses $30,000 =
        # Schedule C line 31 net profit = $90,000 → Schedule 1 line 3.
        # SE base = max(0, 90,000) = 90,000; § 1402(a)(12) SECA base =
        # 90,000 × 0.9235 = $83,115.00; SE tax (below the $176,100 OASDI
        # wage base) = 83,115 × (0.124 + 0.029) = 83,115 × 0.153 =
        # $12,716.595 → $12,716.60 (cents). One-half § 164(f) deduction =
        # 12,716.60 / 2 = $6,358.30.
        # AGI = 90,000 (Schedule 1 line 3) − 6,358.30 = $83,641.70.
        # § 63 taxable income = 83,641.70 − 15,000 (standard deduction) =
        # $68,641.70.
        ff = _final_facts(_freelancer_inputs(schedule_c=_sc("120000.00", "30000.00")))
        self.assertEqual(
            ff["us.stage.schedule_c"]["net_profit_usd"], D("90000.00")
        )
        self.assertEqual(
            ff["us.stage.income_side_inputs"]["schedule_1_other_income_usd"],
            D("90000.00"),
        )
        self.assertEqual(ff["us.stage.se_tax"]["se_tax_usd"], D("12716.60"))
        self.assertEqual(ff["us.stage.adjusted_gross_income"], D("83641.70"))
        self.assertEqual(ff["us.stage.taxable_income"], D("68641.70"))
        # § 1 regular tax via the IRS Tax Table (income < $100,000 uses the
        # $50-bucket midpoint table per the Form 1040 line-16 instructions):
        # $10,012.00 on the $68,641.70 ordinary income.
        self.assertEqual(
            ff["us.stage.regular_tax_before_credits"][
                "regular_tax_before_credits_usd"
            ],
            D("10012.00"),
        )

    def test_loss_is_not_floored_on_schedule_c_itself(self) -> None:
        # § 162-style loss handling on the U.S. side: a Schedule C loss is NOT
        # floored on Schedule C itself — the signed net is what reaches Form
        # 1040 (Schedule 1 line 3). Receipts $10,000 − expenses $14,500 =
        # −$4,500. Exercised at the US25-02A-SCHEDULE-C and
        # US25-02-INCOME-SIDE-INPUTS rule level (the downstream § 904 FTC
        # denominator chain is undefined for an all-loss, zero-other-income
        # filer and is out of scope for this slice).
        from tax_pipeline.y2025.us_rules import (
            us25_02_income_side_inputs,
            us25_02a_schedule_c,
        )

        inputs = _freelancer_inputs(schedule_c=_sc("10000.00", "14500.00"))
        facts = {"us.assessment.inputs": inputs}
        schedule_c = us25_02a_schedule_c(facts)["us.stage.schedule_c"]
        self.assertEqual(schedule_c["net_profit_usd"], D("-4500.00"))
        income_side = us25_02_income_side_inputs(facts)["us.stage.income_side_inputs"]
        # The −$4,500 loss flows (signed) into Schedule 1 line 3 / AGI.
        self.assertEqual(
            income_side["schedule_1_other_income_usd"], D("-4500.00")
        )
        self.assertEqual(income_side["schedule_c_net_profit_usd"], D("-4500.00"))
        # A loss produces no positive net SE earnings → SE base = 0.
        self.assertEqual(inputs.se_inputs.net_se_earnings_usd, D("0.00"))

    def test_wage_earner_has_zero_schedule_c_and_unchanged_baseline(self) -> None:
        # schedule_c_inputs=None → zero net profit → Schedule 1 line 3 = 0,
        # SE base = 0. AGI = 0, taxable income = 0, tax = 0.
        assessment = compute_us_assessment_2025(_freelancer_inputs(schedule_c=None))
        self.assertEqual(
            assessment.regular_tax.schedule_1_other_income_usd, D("0.00")
        )
        self.assertEqual(
            assessment.regular_tax.adjusted_gross_income_usd, D("0.00")
        )
        self.assertEqual(assessment.regular_tax.taxable_income_usd, D("0.00"))


class ScheduleCTotalizationAndIncomeTogetherTest(unittest.TestCase):
    """A German Certificate of Coverage exempts the SE earnings from § 1401
    (Phase 0), but the Schedule C INCOME still flows to U.S. income tax."""

    def test_totalization_exempt_se_but_income_still_taxed(self) -> None:
        # Same $90,000 net profit, but with a German Certificate of Coverage.
        # SE tax = $0 (exempt_under_totalization=True) — the German system
        # covers the freelancer. BUT the income still flows: Schedule 1 line 3
        # = 90,000. With SE tax = 0 there is NO § 164(f) deduction, so:
        # AGI = 90,000; § 63 taxable income = 90,000 − 15,000 = $75,000.
        ff = _final_facts(
            _freelancer_inputs(
                schedule_c=_sc("120000.00", "30000.00"),
                totalization_certificate_present=True,
            )
        )
        # SE tax exempt under the Totalization Agreement (explicit, not zero).
        self.assertEqual(ff["us.stage.se_tax"]["se_tax_usd"], D("0.00"))
        self.assertTrue(ff["us.stage.se_tax"]["exempt_under_totalization"])
        self.assertIn("Totalization", ff["us.stage.se_tax"]["coverage_basis"])
        # Income still flows to AGI / income tax (NOT exempt for income tax).
        self.assertEqual(
            ff["us.stage.income_side_inputs"]["schedule_1_other_income_usd"],
            D("90000.00"),
        )
        self.assertEqual(ff["us.stage.adjusted_gross_income"], D("90000.00"))
        self.assertEqual(ff["us.stage.taxable_income"], D("75000.00"))
        # § 1 tax via the IRS Tax Table on $75,000 ordinary (single):
        # $11,420.00.
        self.assertEqual(
            ff["us.stage.regular_tax_before_credits"][
                "regular_tax_before_credits_usd"
            ],
            D("11420.00"),
        )


class Section199AGrantsZeroForForeignSourceTest(unittest.TestCase):
    """26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c): foreign-source business income
    is NOT QBI → the deduction is not_applicable (ZERO), taxable income
    unchanged. No Form 8995 line is rendered (invariant I13)."""

    def test_qbi_gate_grants_zero_and_does_not_change_taxable_income(self) -> None:
        inputs = _freelancer_inputs(schedule_c=_sc("120000.00", "30000.00"))
        ff = _final_facts(inputs)
        taxable_income = ff["us.stage.taxable_income"]

        # The gate adjudicates § 199A for the same foreign-source business.
        gate = qbi_gate_2025(schedule_c_inputs=inputs.schedule_c_inputs)
        self.assertEqual(gate.status, "not_applicable")
        self.assertFalse(gate.applicable)
        self.assertEqual(gate.qbi_deduction_usd, D("0.00"))
        self.assertEqual(gate.business_income_source, BUSINESS_INCOME_SOURCE_FOREIGN)
        self.assertIn("§ 199A(c)(3)(A)(i)", gate.basis)
        self.assertIn("§ 864(c)", gate.basis)

        # Taxable income with the gate present is the SAME as the § 63 value —
        # § 199A subtracts nothing (no 20% QBI deduction granted).
        self.assertEqual(taxable_income, D("68641.70"))

    def test_qbi_gate_output_in_rule_graph_is_not_applicable(self) -> None:
        inputs = _freelancer_inputs(schedule_c=_sc("120000.00", "30000.00"))
        gate = _final_facts(inputs)["us.stage.qbi_gate"]
        self.assertEqual(gate["status"], "not_applicable")
        self.assertEqual(gate["qbi_deduction_usd"], D("0.00"))
        # § 199A leaves taxable income untouched for foreign source.
        self.assertEqual(
            gate["taxable_income_before_qbi_usd"],
            gate["taxable_income_after_qbi_usd"],
        )

    def test_us_effectively_connected_fails_closed_at_qbi_gate(self) -> None:
        # The QBI-granting path is not modeled — the gate fails closed rather
        # than granting an unverified 20% deduction (a LEAK-class
        # over-deduction).
        with self.assertRaises(NotImplementedError):
            qbi_gate_2025(
                schedule_c_inputs=_sc(
                    "120000.00", "30000.00", "us_effectively_connected"
                )
            )


class ScheduleCDualPathNoDoubleCountTest(unittest.TestCase):
    """The single net profit is income once AND the SE-tax base — not
    double-counted. AGI = Schedule 1 income − ½ SE tax."""

    def test_income_counted_once_se_tax_is_separate(self) -> None:
        ff = _final_facts(_freelancer_inputs(schedule_c=_sc("120000.00", "30000.00")))
        net_profit = D("90000.00")
        half_se_tax = (ff["us.stage.se_tax"]["se_tax_usd"] / D("2")).quantize(
            D("0.01")
        )
        # AGI = net profit (income, once) − ½ SE tax (§ 164(f) deduction).
        self.assertEqual(
            ff["us.stage.adjusted_gross_income"], net_profit - half_se_tax
        )
        # The net profit appears once on Schedule 1 (income); the SE tax is a
        # SEPARATE tax on the same earnings.
        self.assertEqual(
            ff["us.stage.income_side_inputs"]["schedule_1_other_income_usd"],
            net_profit,
        )
        self.assertEqual(ff["us.stage.se_tax"]["net_se_earnings_usd"], net_profit)


class ScheduleCDemoInvarianceTest(unittest.TestCase):
    """The demo workspace is a wage earner (worker_type=employee → no
    Schedule C). Adding US25-02A-SCHEDULE-C + US25-08A-QBI-GATE must leave the
    demo AGI / taxable income / total tax VALUE-identical to the pre-slice
    baseline (CLAUDE.md / spec § 7 demo invariance).

    The full-run byte-identity (AGI 137,335.18 / taxable income 121,585.18 /
    total tax 221.92 / U.S. refund 778.08) is exercised by the demo end-to-end
    run; this test pins the structural invariant the slice could break: a
    wage-earner workspace yields NO Schedule C position (so net profit is zero
    and the SE base falls back to the manual override) and the § 199A gate is
    not_applicable with a zero deduction.
    """

    def test_demo_wage_earner_has_no_schedule_c_and_zero_qbi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            inputs = load_us_assessment_inputs_2025(
                paths, germany_treaty_dividend_items=None
            )
        # Wage earner: no Schedule C position; net profit zero by construction.
        self.assertIsNone(inputs.schedule_c_inputs)
        self.assertEqual(
            schedule_c_net_profit_2025(
                inputs=_sc("0.00", "0.00")
            ).net_profit_usd,
            D("0.00"),
        )
        # § 199A is not_applicable (zero) even for a wage earner with no QBI.
        gate = qbi_gate_2025(schedule_c_inputs=inputs.schedule_c_inputs)
        self.assertEqual(gate.status, "not_applicable")
        self.assertEqual(gate.qbi_deduction_usd, D("0.00"))


class ScheduleCLoaderFailClosedTest(unittest.TestCase):
    """Loader contracts (CLAUDE.md fail-closed posture)."""

    def _demo_with_elections(self, tmp: str, **elections):
        paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
        profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
        profile.setdefault("elections", {}).update(elections)
        paths.profile_path.write_text(json.dumps(profile), encoding="utf-8")
        return paths

    def _write_business_income(self, paths, receipts: str, expenses: str) -> None:
        (paths.config_root / "us-business-income.csv").write_text(
            "key,amount_usd,source,note\n"
            f"gross_receipts_usd,{receipts},test,\n"
            f"business_expenses_usd,{expenses},test,\n",
            encoding="utf-8",
        )

    def test_employee_default_has_no_schedule_c(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertIsNone(inputs.schedule_c_inputs)

    def test_self_employed_loads_business_facts_and_derives_se_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                business_income_source="foreign",
            )
            self._write_business_income(paths, "120000.00", "30000.00")
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertIsNotNone(inputs.schedule_c_inputs)
            self.assertEqual(
                inputs.schedule_c_inputs.gross_receipts_usd, D("120000.00")
            )
            self.assertEqual(
                inputs.schedule_c_inputs.business_expenses_usd, D("30000.00")
            )
            self.assertEqual(
                inputs.schedule_c_inputs.business_income_source,
                BUSINESS_INCOME_SOURCE_FOREIGN,
            )
            # SE base is DERIVED from the Schedule C net profit ($90,000).
            self.assertEqual(
                inputs.se_inputs.net_se_earnings_usd, D("90000.00")
            )

    def test_self_employed_without_facts_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                business_income_source="foreign",
            )
            with self.assertRaisesRegex(ValueError, "us-business-income"):
                load_us_assessment_inputs_2025(paths)

    def test_us_effectively_connected_fails_closed_at_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                business_income_source="us_effectively_connected",
            )
            self._write_business_income(paths, "120000.00", "30000.00")
            with self.assertRaisesRegex(
                NotImplementedError, r"199A|us_effectively_connected"
            ):
                load_us_assessment_inputs_2025(paths)

    def test_self_employed_with_manual_se_override_fails_closed(self) -> None:
        # The SE base must have a single unambiguous source: under a Schedule C
        # position the manual se_net_earnings_usd override may not also be set.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._demo_with_elections(
                tmp,
                worker_type="self_employed",
                business_income_source="foreign",
            )
            self._write_business_income(paths, "120000.00", "30000.00")
            overrides = json.loads(
                paths.manual_overrides_path.read_text(encoding="utf-8")
            )
            overrides["se_net_earnings_usd"] = "50000.00"
            paths.manual_overrides_path.write_text(
                json.dumps(overrides), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "se_net_earnings"):
                load_us_assessment_inputs_2025(paths)


class ScheduleCRendererTest(unittest.TestCase):
    """The Schedule C renderer (``_write_schedule_c``) writes the net-profit
    line via ``legal_value_entry`` (I3 / I11); it is gated on a declared
    Schedule C position (wage earner → form absent, invariant I13)."""

    def test_renderer_writes_schedule_c_lines(self) -> None:
        from tax_pipeline.forms.usa import _write_schedule_c

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            treaty = {
                "schedule_c": {
                    "line_7_gross_income_usd": "120000.00",
                    "line_28_total_expenses_usd": "30000.00",
                    "line_31_net_profit_usd": "90000.00",
                }
            }
            _write_schedule_c(paths, treaty, {}, None)
            form_path = paths.usa_forms_root / f"{paths.year}_schedule_c.md"
            self.assertTrue(form_path.exists())
            text = form_path.read_text(encoding="utf-8")
            # IRS-VERIFIED 2026-06-13 line numbers and values.
            self.assertIn("Line 7", text)
            self.assertIn("120000.00 USD", text)
            self.assertIn("Line 28", text)
            self.assertIn("30000.00 USD", text)
            self.assertIn("Line 31", text)
            self.assertIn("90000.00 USD", text)
            # No Form 8995 line is rendered for foreign-source income (I13);
            # the § 199A non-applicability is narrated, not a zero form line.
            self.assertIn("199A", text)
            self.assertIn("8995", text)  # only the "No Form 8995 is filed" note

    def test_renderer_skips_schedule_c_for_wage_earner(self) -> None:
        from tax_pipeline.forms.usa import _write_schedule_c

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            # Wage-earner posture: zero gross receipts, zero net profit.
            treaty = {
                "schedule_c": {
                    "line_7_gross_income_usd": "0.00",
                    "line_28_total_expenses_usd": "0.00",
                    "line_31_net_profit_usd": "0.00",
                }
            }
            _write_schedule_c(paths, treaty, {}, None)
            form_path = paths.usa_forms_root / f"{paths.year}_schedule_c.md"
            self.assertFalse(
                form_path.exists(),
                "Schedule C should NOT render for a wage earner (no business).",
            )


if __name__ == "__main__":
    unittest.main()
