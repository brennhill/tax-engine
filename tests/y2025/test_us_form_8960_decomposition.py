"""B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 line-level decomposition.

Authority:
- 26 U.S.C. § 1411 — Net Investment Income Tax (3.8 % × min(NII,
  max(0, MAGI − threshold))).
- IRS Form 8960 instructions:
  https://www.irs.gov/forms-pubs/about-form-8960

B5 surfaces the Form 8960 Part I + Part III line-level decomposition as
declared rule outputs so the form-renderer reads each line through a
real ``StageResult.output_fingerprint`` (invariants I2 / I11). The
declared outputs (US25-20-NIIT) are:

  - us.tax.form_8960_line_1_interest_usd
  - us.tax.form_8960_line_2_ordinary_dividends_usd
  - us.tax.form_8960_line_5a_capital_gain_loss_usd
  - us.tax.form_8960_line_5b_non_section_1411_adj_usd        (= 0)
  - us.tax.form_8960_line_5c_cfc_pfic_adj_usd                (= 0)
  - us.tax.form_8960_line_5d_combined_capital_usd            (= 5a + 5b + 5c)
  - us.tax.form_8960_line_7_other_modifications_usd          (substitute payments + optional staking)
  - us.tax.form_8960_line_8_total_investment_income_usd      (= line 1 + line 2 + line 5d + line 7, floored at 0)
  - us.tax.form_8960_line_11_total_deductions_usd            (= 0; no Part II deductions modeled)
  - us.tax.form_8960_line_12_net_investment_income_usd       (= line 8 − line 11)

The B-audit pass (2026-05-03) added line 7 + line 11 because the prior
B5 commit omitted both: line 7 was being summed into line 8 inside the
rule body but was never rendered, so the displayed Part I lines did
not foot to line 8 whenever substitute-payment income was non-zero
(brenn-2025 had $423.24 of line 7 income).
"""
from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tests.y2025._treaty_fixture import write_demo_us_treaty_dividend_items
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_rules import (
    execute_us_rule_graph,
    us_initial_facts_2025,
    us_initial_fingerprints_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


D = Decimal


FORM_8960_OUTPUT_KEYS = (
    "us.tax.form_8960_line_1_interest_usd",
    "us.tax.form_8960_line_2_ordinary_dividends_usd",
    "us.tax.form_8960_line_5a_capital_gain_loss_usd",
    "us.tax.form_8960_line_5b_non_section_1411_adj_usd",
    "us.tax.form_8960_line_5c_cfc_pfic_adj_usd",
    "us.tax.form_8960_line_5d_combined_capital_usd",
    "us.tax.form_8960_line_7_other_modifications_usd",
    "us.tax.form_8960_line_8_total_investment_income_usd",
    "us.tax.form_8960_line_11_total_deductions_usd",
    "us.tax.form_8960_line_12_net_investment_income_usd",
)


class Form8960DeclarationTest(unittest.TestCase):
    """US25-20-NIIT must declare every Form 8960 line-level output."""

    def setUp(self) -> None:
        self.stages = {s.stage_id: s for s in usa_law_stages_2025()}

    def test_stage_declares_all_form_8960_keys(self) -> None:
        stage = self.stages["US25-20-NIIT"]
        for key in FORM_8960_OUTPUT_KEYS:
            self.assertIn(key, stage.output_keys)

    def test_each_line_has_form_line_ref_to_form_8960(self) -> None:
        wanted = {
            "us.tax.form_8960_line_1_interest_usd": "1",
            "us.tax.form_8960_line_2_ordinary_dividends_usd": "2",
            "us.tax.form_8960_line_5a_capital_gain_loss_usd": "5a",
            "us.tax.form_8960_line_5b_non_section_1411_adj_usd": "5b",
            "us.tax.form_8960_line_5c_cfc_pfic_adj_usd": "5c",
            "us.tax.form_8960_line_5d_combined_capital_usd": "5d",
            "us.tax.form_8960_line_7_other_modifications_usd": "7",
            "us.tax.form_8960_line_8_total_investment_income_usd": "8",
            "us.tax.form_8960_line_11_total_deductions_usd": "11",
            "us.tax.form_8960_line_12_net_investment_income_usd": "12",
        }
        seen: set[str] = set()
        for stage in self.stages.values():
            for declaration in stage.outputs:
                if declaration.key in wanted:
                    refs = {(r.form, r.line) for r in declaration.form_line_refs}
                    self.assertIn(("Form 8960", wanted[declaration.key]), refs)
                    seen.add(declaration.key)
        self.assertEqual(seen, set(wanted))

    def test_niit_scalar_also_carries_form_8960_line_17(self) -> None:
        # B5: the existing ``us.tax.schedule_2_line_12_niit_usd`` output
        # gains a Form 8960 line 17 FormLineRef so the renderer can
        # write Schedule 2 line 12 AND Form 8960 line 17 from the same
        # fingerprinted scalar.
        stage = self.stages["US25-20-NIIT"]
        for declaration in stage.outputs:
            if declaration.key == "us.tax.schedule_2_line_12_niit_usd":
                refs = {(r.form, r.line) for r in declaration.form_line_refs}
                self.assertIn(("Schedule 2", "12"), refs)
                self.assertIn(("Form 8960", "17"), refs)
                return
        self.fail("us.tax.schedule_2_line_12_niit_usd not declared on US25-20-NIIT")


class Form8960ValuesTest(unittest.TestCase):
    """Executor materialises all eight keys; values match expected
    semantics in the demo posture (zero interest/SE, non-zero ordinary
    dividends, capital gain/loss).
    """

    def _executed_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            write_demo_us_treaty_dividend_items(paths)
            inputs = load_us_assessment_inputs_2025(
                paths,
                germany_treaty_dividend_items=(
                    GermanyUSTreatyDividendPacketItem2025(
                        item_id="msft_us_dividend",
                        owner_slot="person_1",
                        dividend_class="portfolio_dividend",
                        gross_dividend_eur=D("280.00"),
                        german_taxable_dividend_eur=D("280.00"),
                        article_10_source_tax_ceiling_eur=D("42.00"),
                        germany_precredit_tax_eur=D("36.25"),
                        germany_residence_credit_eur=D("36.25"),
                    ),
                ),
            )
        initial_facts = us_initial_facts_2025(inputs)
        execution = execute_us_rule_graph(
            initial_facts,
            input_fingerprints=us_initial_fingerprints_2025(initial_facts),
        )
        return execution

    def test_executor_materializes_all_keys(self) -> None:
        execution = self._executed_facts()
        for key in FORM_8960_OUTPUT_KEYS:
            self.assertIn(key, execution.final_facts)

    def test_line_8_foots_from_lines_1_2_5d_7(self) -> None:
        """B-audit reconciliation: rendered Part I lines (1, 2, 5d, 7)
        must sum (floored at 0) to line 8 — without line 7 the
        rendered components silently undershot whenever substitute-
        payment / staking income was non-zero.
        """
        execution = self._executed_facts()
        line_1 = execution.final_facts["us.tax.form_8960_line_1_interest_usd"]
        line_2 = execution.final_facts["us.tax.form_8960_line_2_ordinary_dividends_usd"]
        line_5d = execution.final_facts["us.tax.form_8960_line_5d_combined_capital_usd"]
        line_7 = execution.final_facts["us.tax.form_8960_line_7_other_modifications_usd"]
        line_8 = execution.final_facts[
            "us.tax.form_8960_line_8_total_investment_income_usd"
        ]
        signed = (line_1 + line_2 + line_5d + line_7).quantize(D("0.01"))
        expected = signed if signed > D("0") else D("0.00")
        self.assertEqual(line_8, expected)

    def test_line_12_foots_from_line_8_minus_line_11(self) -> None:
        execution = self._executed_facts()
        line_8 = execution.final_facts[
            "us.tax.form_8960_line_8_total_investment_income_usd"
        ]
        line_11 = execution.final_facts[
            "us.tax.form_8960_line_11_total_deductions_usd"
        ]
        line_12 = execution.final_facts[
            "us.tax.form_8960_line_12_net_investment_income_usd"
        ]
        self.assertEqual(line_12, (line_8 - line_11).quantize(D("0.01")))

    def test_line_5d_equals_5a_plus_5b_plus_5c(self) -> None:
        execution = self._executed_facts()
        line_5a = execution.final_facts[
            "us.tax.form_8960_line_5a_capital_gain_loss_usd"
        ]
        line_5b = execution.final_facts[
            "us.tax.form_8960_line_5b_non_section_1411_adj_usd"
        ]
        line_5c = execution.final_facts["us.tax.form_8960_line_5c_cfc_pfic_adj_usd"]
        line_5d = execution.final_facts[
            "us.tax.form_8960_line_5d_combined_capital_usd"
        ]
        self.assertEqual(line_5d, (line_5a + line_5b + line_5c).quantize(D("0.01")))

    def test_line_5b_5c_are_zero_in_supported_posture(self) -> None:
        # No non-§ 1411 trade/business adjustments and no CFC/PFIC
        # adjustments modelled in the supported posture.
        execution = self._executed_facts()
        self.assertEqual(
            execution.final_facts["us.tax.form_8960_line_5b_non_section_1411_adj_usd"],
            D("0.00"),
        )
        self.assertEqual(
            execution.final_facts["us.tax.form_8960_line_5c_cfc_pfic_adj_usd"],
            D("0.00"),
        )

    def test_line_12_equals_line_8_in_supported_posture(self) -> None:
        # No Part II investment-expense deductions modelled, so line 12
        # = line 8.
        execution = self._executed_facts()
        self.assertEqual(
            execution.final_facts[
                "us.tax.form_8960_line_12_net_investment_income_usd"
            ],
            execution.final_facts[
                "us.tax.form_8960_line_8_total_investment_income_usd"
            ],
        )

    def test_line_12_equals_existing_net_investment_income(self) -> None:
        # Reconciliation: line 12 must agree with the legacy
        # ``us.stage.niit.net_investment_income_usd`` scalar to the
        # cent.
        execution = self._executed_facts()
        niit = execution.final_facts["us.stage.niit"]
        self.assertEqual(
            execution.final_facts[
                "us.tax.form_8960_line_12_net_investment_income_usd"
            ],
            niit["net_investment_income_usd"],
        )


class Form8960RendererEmitsLinesTest(unittest.TestCase):
    """Renderer-side: ``_write_form_8960`` must emit a markdown row for
    every Form 8960 line surfaced (1, 2, 5a-5d, 8, 12, 17).
    """

    def test_renderer_emits_all_form_8960_lines(self) -> None:
        from tax_pipeline.run_year import run_year

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            write_demo_us_treaty_dividend_items(paths)
            run_year(Path(tmp), "2025", workspace_root=paths.year_root)
            form_8960_md = (
                paths.usa_forms_root / f"{paths.year}_form_8960.md"
            ).read_text(encoding="utf-8")

        for label in (
            "Line 1",
            "Line 2",
            "Line 5a",
            "Line 5b",
            "Line 5c",
            "Line 5d",
            "Line 7",
            "Line 8",
            "Line 11",
            "Line 12",
            "Line 17",
        ):
            self.assertIn(label, form_8960_md)
        self.assertIn("https://www.irs.gov/forms-pubs/about-form-8960", form_8960_md)


if __name__ == "__main__":
    unittest.main()
