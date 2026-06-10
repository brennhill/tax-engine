"""B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 line-level decomposition.

Authority:
- 26 U.S.C. § 3101(b)(2) — 0.9 % Additional Medicare Tax on Medicare-
  taxable wages above the filing-status threshold (Form 8959 Part I).
- 26 U.S.C. § 1401(b)(2) — same 0.9 % on net SE earnings; shares the
  threshold with § 3101(b)(2) (Form 8959 Part II).
- IRS Form 8959 instructions:
  https://www.irs.gov/forms-pubs/about-form-8959

B3 surfaces the Form 8959 line-level decomposition as declared rule
outputs so the form-renderer reads each line through a real
``StageResult.output_fingerprint`` (invariants I2 / I11). Form 8959
splits the combined excess into Part I (wages-portion) and Part II
(SE-portion) using a single shared threshold consumed wages-first.

The new declared outputs (US25-ADDITIONAL-MEDICARE) are:

  - us.tax.form_8959_line_1_medicare_wages_usd          (Part I, line 1)
  - us.tax.form_8959_line_4_total_medicare_wages_usd    (Part I, line 4 = sum of lines 1-3)
  - us.tax.form_8959_line_5_threshold_usd               (Part I, line 5 = filing-status threshold)
  - us.tax.form_8959_line_6_wages_excess_usd            (Part I, line 6 = max(0, line 4 − line 5))
  - us.tax.form_8959_line_7_addtl_medicare_on_wages_usd (Part I, line 7 = line 6 × 0.009)
  - us.tax.form_8959_line_8_se_taxable_usd              (Part II, line 8)
  - us.tax.form_8959_line_11_residual_threshold_usd     (Part II, line 11 = max(0, threshold − wages))
  - us.tax.form_8959_line_13_addtl_medicare_on_se_usd   (Part II, line 13)
  - us.tax.form_8959_line_18_total_addtl_medicare_usd   (line 18 = line 7 + line 13 + line 17)
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
from tax_pipeline.y2025.us_law import (
    ADDITIONAL_MEDICARE_RATE,
    USSelfEmploymentInputs2025,
    round_cents,
)
from tax_pipeline.y2025.us_rules import (
    execute_us_rule_graph,
    us_initial_facts_2025,
    us_initial_fingerprints_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


D = Decimal


FORM_8959_OUTPUT_KEYS = (
    "us.tax.form_8959_line_1_medicare_wages_usd",
    "us.tax.form_8959_line_4_total_medicare_wages_usd",
    "us.tax.form_8959_line_5_threshold_usd",
    "us.tax.form_8959_line_6_wages_excess_usd",
    "us.tax.form_8959_line_7_addtl_medicare_on_wages_usd",
    "us.tax.form_8959_line_8_se_taxable_usd",
    "us.tax.form_8959_line_11_residual_threshold_usd",
    "us.tax.form_8959_line_13_addtl_medicare_on_se_usd",
    "us.tax.form_8959_line_18_total_addtl_medicare_usd",
)


class Form8959DeclarationTest(unittest.TestCase):
    """The producing stage US25-ADDITIONAL-MEDICARE must declare every
    Form 8959 line-level output in its ``output_keys`` (and therefore in
    ``OutputDeclaration``).
    """

    def setUp(self) -> None:
        self.stages = {s.stage_id: s for s in usa_law_stages_2025()}

    def test_stage_declares_all_nine_form_8959_keys(self) -> None:
        stage = self.stages["US25-ADDITIONAL-MEDICARE"]
        for key in FORM_8959_OUTPUT_KEYS:
            self.assertIn(key, stage.output_keys)

    def test_each_line_has_form_line_ref_to_form_8959(self) -> None:
        wanted = {
            "us.tax.form_8959_line_1_medicare_wages_usd": "1",
            "us.tax.form_8959_line_4_total_medicare_wages_usd": "4",
            "us.tax.form_8959_line_5_threshold_usd": "5",
            "us.tax.form_8959_line_6_wages_excess_usd": "6",
            "us.tax.form_8959_line_7_addtl_medicare_on_wages_usd": "7",
            "us.tax.form_8959_line_8_se_taxable_usd": "8",
            "us.tax.form_8959_line_11_residual_threshold_usd": "11",
            "us.tax.form_8959_line_13_addtl_medicare_on_se_usd": "13",
            "us.tax.form_8959_line_18_total_addtl_medicare_usd": "18",
        }
        seen: set[str] = set()
        for stage in self.stages.values():
            for declaration in stage.outputs:
                if declaration.key in wanted:
                    refs = {(r.form, r.line) for r in declaration.form_line_refs}
                    self.assertIn(("Form 8959", wanted[declaration.key]), refs)
                    seen.add(declaration.key)
        self.assertEqual(seen, set(wanted))


class Form8959ZeroPostureTest(unittest.TestCase):
    """Demo posture has zero Medicare wages and zero SE earnings, so
    every Form 8959 dollar-valued line is zero. The threshold (line 5)
    is the only non-zero scalar.
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

    def test_executor_materializes_all_nine_keys(self) -> None:
        execution = self._executed_facts()
        for key in FORM_8959_OUTPUT_KEYS:
            self.assertIn(key, execution.final_facts)

    def test_demo_posture_line_18_is_zero(self) -> None:
        execution = self._executed_facts()
        self.assertEqual(
            execution.final_facts["us.tax.form_8959_line_18_total_addtl_medicare_usd"],
            D("0.00"),
        )


class Form8959NonZeroDecompositionTest(unittest.TestCase):
    """Drive ``us25_additional_medicare(facts)`` directly with a hand-
    built facts dict to exercise the Form 8959 wages-first / SE-second
    decomposition. Avoids running the full graph (which would fail on
    unrelated posture invariants for synthetic SE postures).
    """

    def _build_facts(
        self, *, medicare_wages: Decimal, se_taxable: Decimal,
        filing_status: str = "Single",
    ):
        from dataclasses import replace
        from tax_pipeline.demo_workspace import materialize_demo_workspace
        from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            write_demo_us_treaty_dividend_items(paths)
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
                net_se_earnings_usd=D("0.00"),
                us_w2_medicare_taxable_wages_usd=medicare_wages,
                totalization_certificate_present=False,
            ),
            profile=replace(base.profile, filing_status_label=filing_status),
        )
        # us25_additional_medicare reads facts["us.assessment.inputs"] and
        # facts["us.stage.se_tax"]. Provide both directly.
        return {
            "us.assessment.inputs": inputs,
            "us.stage.se_tax": {
                "se_taxable_earnings_usd": se_taxable,
                # Other keys are unused by us25_additional_medicare.
                "net_se_earnings_usd": D("0.00"),
                "oasdi_taxable_earnings_usd": D("0.00"),
                "oasdi_tax_usd": D("0.00"),
                "medicare_tax_usd": D("0.00"),
                "se_tax_usd": D("0.00"),
            },
        }

    def _run_rule(self, *, medicare_wages: Decimal, se_taxable: Decimal,
                  filing_status: str = "Single") -> dict:
        from tax_pipeline.y2025.us_rules import us25_additional_medicare

        facts = self._build_facts(
            medicare_wages=medicare_wages,
            se_taxable=se_taxable,
            filing_status=filing_status,
        )
        return us25_additional_medicare(facts)

    def test_wages_above_threshold_only(self) -> None:
        # Wages $250,000, SE_taxable 0. Single threshold = $200,000.
        # Line 6 = 50,000; Line 7 = 50,000 × 0.009 = 450.00.
        # Line 11 = 0; Line 13 = 0; Line 18 = 450.00.
        outputs = self._run_rule(
            medicare_wages=D("250000.00"), se_taxable=D("0.00")
        )
        self.assertEqual(outputs["us.tax.form_8959_line_6_wages_excess_usd"], D("50000.00"))
        self.assertEqual(
            outputs["us.tax.form_8959_line_7_addtl_medicare_on_wages_usd"],
            round_cents(D("50000.00") * ADDITIONAL_MEDICARE_RATE),
        )
        self.assertEqual(outputs["us.tax.form_8959_line_11_residual_threshold_usd"], D("0.00"))
        self.assertEqual(outputs["us.tax.form_8959_line_13_addtl_medicare_on_se_usd"], D("0.00"))
        self.assertEqual(
            outputs["us.tax.form_8959_line_18_total_addtl_medicare_usd"],
            round_cents(D("50000.00") * ADDITIONAL_MEDICARE_RATE),
        )

    def test_wages_above_threshold_and_se_present(self) -> None:
        # Wages $250,000, SE_taxable $27,705 (= 30,000 × 0.9235).
        # Line 6 = 50,000; Line 7 = 450.00.
        # Line 11 = 0; Line 12 = 27,705; Line 13 = 27,705 × 0.009 = 249.35.
        outputs = self._run_rule(
            medicare_wages=D("250000.00"), se_taxable=D("27705.00")
        )
        self.assertEqual(outputs["us.tax.form_8959_line_6_wages_excess_usd"], D("50000.00"))
        self.assertEqual(
            outputs["us.tax.form_8959_line_7_addtl_medicare_on_wages_usd"],
            round_cents(D("50000.00") * ADDITIONAL_MEDICARE_RATE),
        )
        self.assertEqual(outputs["us.tax.form_8959_line_11_residual_threshold_usd"], D("0.00"))
        expected_line_13 = round_cents(D("27705.00") * ADDITIONAL_MEDICARE_RATE)
        self.assertEqual(outputs["us.tax.form_8959_line_13_addtl_medicare_on_se_usd"], expected_line_13)

    def test_se_only_below_threshold_yields_zero(self) -> None:
        # Wages 0, SE_taxable $27,705. Residual threshold = $200,000.
        # Line 12 = max(0, 27,705 − 200,000) = 0 → line 18 = 0.
        outputs = self._run_rule(
            medicare_wages=D("0.00"), se_taxable=D("27705.00")
        )
        self.assertEqual(
            outputs["us.tax.form_8959_line_18_total_addtl_medicare_usd"],
            D("0.00"),
        )

    def test_wages_partial_then_se_picks_up_residual(self) -> None:
        # Wages $100,000, SE_taxable $184,700.
        # Line 11 = max(0, 200,000 − 100,000) = 100,000.
        # Line 12 = max(0, 184,700 − 100,000) = 84,700.
        # Line 13 = 84,700 × 0.009.
        outputs = self._run_rule(
            medicare_wages=D("100000.00"), se_taxable=D("184700.00")
        )
        self.assertEqual(
            outputs["us.tax.form_8959_line_7_addtl_medicare_on_wages_usd"], D("0.00")
        )
        self.assertEqual(
            outputs["us.tax.form_8959_line_11_residual_threshold_usd"], D("100000.00")
        )
        expected_line_13 = round_cents(D("84700.00") * ADDITIONAL_MEDICARE_RATE)
        self.assertEqual(
            outputs["us.tax.form_8959_line_13_addtl_medicare_on_se_usd"], expected_line_13
        )


class Form8959RendererEmitsLinesTest(unittest.TestCase):
    """Renderer-side: ``_write_form_8959`` is gated on Schedule 2 line
    11 > 0. In the demo posture (zero Additional Medicare Tax) the form
    file is NOT written. We test the gating behaviour directly.
    """

    def test_renderer_skips_form_8959_when_zero(self) -> None:
        from tax_pipeline.run_year import run_year

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            write_demo_us_treaty_dividend_items(paths)
            run_year(Path(tmp), "2025", workspace_root=paths.year_root)
            form_8959_path = (
                paths.usa_forms_root / f"{paths.year}_form_8959.md"
            )
            self.assertFalse(
                form_8959_path.exists(),
                "Form 8959 should NOT render when Additional Medicare = 0.",
            )


if __name__ == "__main__":
    unittest.main()
