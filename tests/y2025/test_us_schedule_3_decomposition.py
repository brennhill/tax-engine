"""B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line-level decomposition.

Authority:
- 26 U.S.C. §§ 901, 904 — Foreign Tax Credit (Schedule 3 line 1).
- 26 U.S.C. § 904(d)(6) — treaty re-sourcing basket.
- IRS Publication 514 worksheet line 21 — treaty re-sourcing add-on
  (audit row — Form 1116 line 12, NOT Schedule 3 line 11).
  https://www.irs.gov/publications/p514
- IRS Schedule 3 (2024 revision; 2025 retains the line numbering at
  publication time):
  https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
- IRS Form 1116:
  https://www.irs.gov/forms-pubs/about-form-1116

B2 surfaces the Schedule 3 line-level decomposition as declared rule
outputs so the form-renderer reads each line through a real
``StageResult.output_fingerprint`` (invariants I2 / I11). The declared
outputs are:

  - ``us.tax.schedule_3_line_1_ftc_total_usd`` (US25-19A)
  - ``us.tax.pub_514_worksheet_line_21_treaty_resourcing_additional_ftc_usd``
    (US25-21-PAYMENTS) — audit row, Form 1116 line 12.

The Pub. 514 worksheet line 21 add-on is NOT surfaced as a Schedule 3
line because Schedule 3 line 11 per the IRS form numbering is "Excess
Social Security and Tier 1 RRTA tax withheld" (Part II — refundable
credits / payments), unrelated to the FTC. Likewise, Schedule 3 line
6c is the Adoption credit (Form 8839), not "other refundable credits".
The treaty re-sourcing add-on flows into Form 1116 Part III line 12 /
Part IV line 32 (subject to the Form 1116 line 33 cap) and reaches
Schedule 3 only via line 1 (the post-cap allowed FTC).

The B2 change ALSO removes the long-standing I5 smell at
``tax_pipeline/pipelines/y2025/us_treaty_packet.py:147`` where the
projection summed three rule outputs (allowed_general + allowed_passive
+ treaty_resourcing_additional) into a local. The arithmetic now lives
inside the rule graph (US25-19A) under
``us.tax.schedule_3_line_1_ftc_total_usd``.
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


class Schedule3LineDeclarationTest(unittest.TestCase):
    """Producing stages must declare the new ``us.tax.schedule_3_*``
    outputs in their ``output_keys`` (and therefore in
    ``OutputDeclaration``).
    """

    def setUp(self) -> None:
        self.stages = {s.stage_id: s for s in usa_law_stages_2025()}

    def test_us25_19a_declares_schedule_3_line_1(self) -> None:
        stage = self.stages["US25-19A-ALLOWED-FTC-AFTER-RESOURCING"]
        self.assertIn("us.tax.schedule_3_line_1_ftc_total_usd", stage.output_keys)

    def test_no_bogus_schedule_3_line_6c_or_line_11_outputs(self) -> None:
        """Per IRS Schedule 3 (2024 / 2025) line numbering, line 6c is
        the Adoption credit (Part I) and line 11 is "Excess Social
        Security and Tier 1 RRTA tax withheld" (Part II) — neither is
        the treaty FTC add-on. The engine must not declare keys that
        falsely claim those line numbers.
        """
        bogus_keys = {
            "us.tax.schedule_3_line_6c_other_refundable_credits_usd",
            "us.tax.schedule_3_line_11_treaty_resourcing_additional_ftc_usd",
        }
        for stage in self.stages.values():
            declared = {decl.key for decl in stage.outputs}
            self.assertFalse(
                declared & bogus_keys,
                f"{stage.stage_id} must not declare {declared & bogus_keys}",
            )

    def test_form_line_refs_for_schedule_3_outputs(self) -> None:
        # I3: every declared Schedule 3 output must carry a FormLineRef
        # the renderer transits.
        wanted: dict[str, set[tuple[str, str]]] = {
            "us.tax.schedule_3_line_1_ftc_total_usd": {
                ("Schedule 3", "1"),
                # Line 8 mirrors line 1 (Part I total = sum of lines 1-7;
                # only line 1 is non-zero in the supported posture).
                ("Schedule 3", "8"),
            },
        }
        seen: set[str] = set()
        for stage in self.stages.values():
            for declaration in stage.outputs:
                if declaration.key in wanted:
                    refs = {(r.form, r.line) for r in declaration.form_line_refs}
                    self.assertTrue(
                        wanted[declaration.key].issubset(refs),
                        f"{declaration.key} must declare FormLineRefs "
                        f"{wanted[declaration.key]}; got {refs}",
                    )
                    seen.add(declaration.key)
        self.assertEqual(seen, set(wanted))


class Schedule3LineValuesTest(unittest.TestCase):
    """Executor materialises the new keys; values match expected
    semantics (line 1 = post-treaty FTC; line 6c = 0; line 11 = Pub. 514
    worksheet line 21).
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

    def test_executor_materializes_keys(self) -> None:
        execution = self._executed_facts()
        for key in (
            "us.tax.schedule_3_line_1_ftc_total_usd",
        ):
            self.assertIn(key, execution.final_facts)

    def test_no_bogus_schedule_3_outputs_in_final_facts(self) -> None:
        execution = self._executed_facts()
        for bogus in (
            "us.tax.schedule_3_line_6c_other_refundable_credits_usd",
            "us.tax.schedule_3_line_11_treaty_resourcing_additional_ftc_usd",
            # The audit-row variant introduced and rolled back during
            # the B-audit pass also must not exist.
            "us.tax.pub_514_worksheet_line_21_treaty_resourcing_additional_ftc_usd",
        ):
            self.assertNotIn(bogus, execution.final_facts)

    def test_line_1_equals_post_treaty_allowed_ftc(self) -> None:
        # Schedule 3 line 1 = Form 1116 line 33 = post-treaty allowed FTC
        # = baseline allowed FTC + Pub. 514 worksheet line 21 add-on.
        execution = self._executed_facts()
        post_treaty = execution.final_facts[
            "us.stage.total_allowed_ftc_after_treaty_resourcing_usd"
        ]["total_allowed_ftc_after_treaty_resourcing_usd"]
        self.assertEqual(
            execution.final_facts["us.tax.schedule_3_line_1_ftc_total_usd"],
            post_treaty,
        )

    def test_treaty_additional_ftc_still_carries_worksheet_line_21(self) -> None:
        # The Pub. 514 worksheet line 21 add-on remains available via
        # the existing US25-18 stage output (no parallel Schedule-3-
        # facing surface needed).
        execution = self._executed_facts()
        treaty_additional = execution.final_facts["us.stage.treaty_additional_ftc"]
        self.assertIn(
            "worksheet_line_21_additional_credit_usd",
            treaty_additional,
        )


class US25_19A_RemovesProjectionSmellTest(unittest.TestCase):
    """B2 closes the I5 smell at ``us_treaty_packet.py:147`` by promoting
    the Schedule 3 line 1 sum into the rule graph. Verify the rule
    output equals what the previous projection-side sum produced.
    """

    def test_line_1_equals_legacy_three_term_sum(self) -> None:
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
        outputs_by_stage = {r.stage_id: r.outputs for r in execution.stage_results}
        baseline = outputs_by_stage["US25-14-BASELINE-ALLOWED-FTC"][
            "us.stage.baseline_allowed_ftc"
        ]
        treaty_additional = outputs_by_stage["US25-18-TREATY-ADDITIONAL-FTC"][
            "us.stage.treaty_additional_ftc"
        ]
        legacy_sum = (
            baseline["allowed_general_ftc_usd"]
            + baseline["allowed_passive_ftc_usd"]
            + treaty_additional["treaty_resourcing_additional_ftc_usd"]
        ).quantize(D("0.01"))
        self.assertEqual(
            execution.final_facts["us.tax.schedule_3_line_1_ftc_total_usd"],
            legacy_sum,
        )


class Schedule3RendererEmitsLinesTest(unittest.TestCase):
    """Renderer-side: ``_write_schedule_3`` must emit a markdown row for
    every declared Schedule 3 line.
    """

    def test_renderer_emits_all_schedule_3_lines(self) -> None:
        from tax_pipeline.run_year import run_year

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            write_demo_us_treaty_dividend_items(paths)
            run_year(Path(tmp), "2025", workspace_root=paths.year_root)
            schedule_3_md = (
                paths.usa_forms_root / f"{paths.year}_schedule_3.md"
            ).read_text(encoding="utf-8")

        for label in ("Line 1", "Line 8"):
            self.assertIn(label, schedule_3_md)
        # Negative assertion: must NOT label any row as Schedule 3 line
        # 6c or line 11 (those line numbers belong to the Adoption
        # credit and Excess SS/RRTA, respectively — not the FTC add-on).
        self.assertNotIn("| Line 6c", schedule_3_md)
        self.assertNotIn("| Line 11", schedule_3_md)
        self.assertIn(
            "https://www.irs.gov/pub/irs-pdf/f1040s3.pdf",
            schedule_3_md,
        )


if __name__ == "__main__":
    unittest.main()
