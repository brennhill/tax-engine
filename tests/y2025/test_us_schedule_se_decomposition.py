"""B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level decomposition.

Authority:
- 26 U.S.C. § 1401 — 12.4 % OASDI on net SE earnings up to the SSA wage
  base + 2.9 % Medicare on all net SE earnings.
- 26 U.S.C. § 1402(a)(12) — net SE earnings × 92.35 %.
- IRS Schedule SE instructions:
  https://www.irs.gov/forms-pubs/about-schedule-se-form-1040

B4 surfaces the Schedule SE line-level decomposition as declared rule
outputs so the Schedule SE renderer reads each line through a real
``StageResult.output_fingerprint`` (invariants I2 / I11). The new
declared outputs (US25-SE-TAX) are:

  - us.tax.schedule_se_line_2_net_se_earnings_usd
  - us.tax.schedule_se_line_3_total_se_earnings_usd
  - us.tax.schedule_se_line_4a_se_taxable_usd
  - us.tax.schedule_se_line_4c_se_taxable_usd
  - us.tax.schedule_se_line_6_combined_se_base_usd
  - us.tax.schedule_se_line_8a_w2_ss_wages_usd
  - us.tax.schedule_se_line_10_oasdi_tax_usd
  - us.tax.schedule_se_line_11_medicare_tax_usd
  - us.tax.schedule_se_line_12_total_se_tax_usd
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_law import (
    MEDICARE_RATE,
    OASDI_RATE,
    SECA_NET_EARNINGS_FACTOR,
    USSelfEmploymentInputs2025,
    round_cents,
)
from tax_pipeline.y2025.us_rules import us25_se_tax
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


D = Decimal


SCHEDULE_SE_OUTPUT_KEYS = (
    "us.tax.schedule_se_line_2_net_se_earnings_usd",
    "us.tax.schedule_se_line_3_total_se_earnings_usd",
    "us.tax.schedule_se_line_4a_se_taxable_usd",
    "us.tax.schedule_se_line_4c_se_taxable_usd",
    "us.tax.schedule_se_line_6_combined_se_base_usd",
    "us.tax.schedule_se_line_8a_w2_ss_wages_usd",
    "us.tax.schedule_se_line_10_oasdi_tax_usd",
    "us.tax.schedule_se_line_11_medicare_tax_usd",
    "us.tax.schedule_se_line_12_total_se_tax_usd",
)


class ScheduleSEDeclarationTest(unittest.TestCase):
    """US25-SE-TAX must declare every Schedule SE line-level output."""

    def setUp(self) -> None:
        self.stages = {s.stage_id: s for s in usa_law_stages_2025()}

    def test_stage_declares_all_nine_schedule_se_keys(self) -> None:
        stage = self.stages["US25-SE-TAX"]
        for key in SCHEDULE_SE_OUTPUT_KEYS:
            self.assertIn(key, stage.output_keys)

    def test_each_line_has_form_line_ref_to_schedule_se(self) -> None:
        wanted = {
            "us.tax.schedule_se_line_2_net_se_earnings_usd": "2",
            "us.tax.schedule_se_line_3_total_se_earnings_usd": "3",
            "us.tax.schedule_se_line_4a_se_taxable_usd": "4a",
            "us.tax.schedule_se_line_4c_se_taxable_usd": "4c",
            "us.tax.schedule_se_line_6_combined_se_base_usd": "6",
            "us.tax.schedule_se_line_8a_w2_ss_wages_usd": "8a",
            "us.tax.schedule_se_line_10_oasdi_tax_usd": "10",
            "us.tax.schedule_se_line_11_medicare_tax_usd": "11",
            "us.tax.schedule_se_line_12_total_se_tax_usd": "12",
        }
        seen: set[str] = set()
        for stage in self.stages.values():
            for declaration in stage.outputs:
                if declaration.key in wanted:
                    refs = {(r.form, r.line) for r in declaration.form_line_refs}
                    self.assertIn(
                        ("Schedule SE", wanted[declaration.key]), refs
                    )
                    seen.add(declaration.key)
        self.assertEqual(seen, set(wanted))


class ScheduleSEZeroPostureTest(unittest.TestCase):
    """Demo / brenn-2025 postures have zero net SE earnings — every
    Schedule SE dollar-valued line is zero.
    """

    def _executed_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
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
        from tax_pipeline.y2025.us_rules import (
            execute_us_rule_graph,
            us_initial_facts_2025,
            us_initial_fingerprints_2025,
        )

        initial_facts = us_initial_facts_2025(inputs)
        execution = execute_us_rule_graph(
            initial_facts,
            input_fingerprints=us_initial_fingerprints_2025(initial_facts),
        )
        return execution

    def test_executor_materializes_all_nine_keys(self) -> None:
        execution = self._executed_facts()
        for key in SCHEDULE_SE_OUTPUT_KEYS:
            self.assertIn(key, execution.final_facts)

    def test_demo_posture_line_12_is_zero(self) -> None:
        execution = self._executed_facts()
        self.assertEqual(
            execution.final_facts["us.tax.schedule_se_line_12_total_se_tax_usd"],
            D("0.00"),
        )


class ScheduleSENonZeroDecompositionTest(unittest.TestCase):
    """Drive ``us25_se_tax(facts)`` directly with hand-built inputs to
    exercise the line-by-line semantics without running the full graph.
    """

    def _build_facts(self, *, net_se: Decimal, w2_medicare_wages: Decimal):
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            base = load_us_assessment_inputs_2025(
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
        inputs = replace(
            base,
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=net_se,
                us_w2_medicare_taxable_wages_usd=w2_medicare_wages,
                totalization_certificate_present=False,
            ),
        )
        return {"us.assessment.inputs": inputs}

    def test_se_50000_no_w2_wages(self) -> None:
        # Net SE = $50,000. Line 4a = 50,000 × 0.9235 = $46,175.
        # Line 6 = $46,175. Line 8a = 0. Line 9 = $176,100.
        # Line 10 = min(46,175, 176,100) × 0.124 = $5,725.70.
        # Line 11 = 46,175 × 0.029 = $1,339.08 (round-half-up).
        # Line 12 = 5,725.70 + 1,339.08 = $7,064.78.
        outputs = us25_se_tax(
            self._build_facts(net_se=D("50000.00"), w2_medicare_wages=D("0.00"))
        )
        line_4a = outputs["us.tax.schedule_se_line_4a_se_taxable_usd"]
        line_6 = outputs["us.tax.schedule_se_line_6_combined_se_base_usd"]
        line_10 = outputs["us.tax.schedule_se_line_10_oasdi_tax_usd"]
        line_11 = outputs["us.tax.schedule_se_line_11_medicare_tax_usd"]
        line_12 = outputs["us.tax.schedule_se_line_12_total_se_tax_usd"]
        expected_line_4a = round_cents(D("50000.00") * SECA_NET_EARNINGS_FACTOR)
        self.assertEqual(line_4a, expected_line_4a)
        self.assertEqual(line_6, expected_line_4a)
        # OASDI base capped at SSA wage base; below cap, just line 6 × 0.124.
        self.assertEqual(line_10, round_cents(expected_line_4a * OASDI_RATE))
        self.assertEqual(line_11, round_cents(expected_line_4a * MEDICARE_RATE))
        self.assertEqual(line_12, round_cents(line_10 + line_11))

    def test_se_above_wage_base_caps_oasdi(self) -> None:
        # Net SE = $300,000. SE_taxable = 300,000 × 0.9235 = $277,050.
        # Line 6 = $277,050. Line 9 = SS wage base = $176,100.
        # Line 10 = min(277,050, 176,100) × 0.124 = $21,836.40.
        # Line 11 = 277,050 × 0.029.
        outputs = us25_se_tax(
            self._build_facts(net_se=D("300000.00"), w2_medicare_wages=D("0.00"))
        )
        line_10 = outputs["us.tax.schedule_se_line_10_oasdi_tax_usd"]
        # OASDI cap = $176,100 × 0.124.
        self.assertEqual(line_10, round_cents(D("176100.00") * OASDI_RATE))

    def test_line_12_equals_line_10_plus_line_11(self) -> None:
        outputs = us25_se_tax(
            self._build_facts(net_se=D("75000.00"), w2_medicare_wages=D("0.00"))
        )
        self.assertEqual(
            outputs["us.tax.schedule_se_line_12_total_se_tax_usd"],
            round_cents(
                outputs["us.tax.schedule_se_line_10_oasdi_tax_usd"]
                + outputs["us.tax.schedule_se_line_11_medicare_tax_usd"]
            ),
        )


class ScheduleSERendererGatingTest(unittest.TestCase):
    """Renderer-side: Schedule SE is gated on net SE earnings > 0. Demo
    posture has zero SE income → form file is not written.
    """

    def test_renderer_skips_schedule_se_when_zero(self) -> None:
        from tax_pipeline.run_year import run_year

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            run_year(Path(tmp), "2025", workspace_root=paths.year_root)
            schedule_se_path = paths.usa_forms_root / f"{paths.year}_schedule_se.md"
            self.assertFalse(
                schedule_se_path.exists(),
                "Schedule SE should NOT render when net SE earnings = 0.",
            )


if __name__ == "__main__":
    unittest.main()
