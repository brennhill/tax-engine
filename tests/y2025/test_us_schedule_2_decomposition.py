"""B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line-level decomposition.

Authority:
- 26 U.S.C. § 55 — Alternative Minimum Tax (Schedule 2 line 2 on the
  2025 revision; was line 1 on the 2024 revision).
  https://www.law.cornell.edu/uscode/text/26/55
- 26 U.S.C. § 1401 / § 1402 — Self-Employment Tax (Schedule 2 line 4).
- 26 U.S.C. § 3101(b)(2) / § 1401(b)(2) — Additional Medicare
  (Schedule 2 line 11).
- 26 U.S.C. § 1411 — Net Investment Income Tax (Schedule 2 line 12).
- IRS-VERIFIED 2026-05-10 — IRS Schedule 2 (2025 revision):
  https://www.irs.gov/pub/irs-pdf/f1040s2.pdf — Part I lines 1a-1f /
  1y / 1z = additions to tax (APTC repayment, clean-vehicle credit
  repayments, Form 4255 EPE recapture, other), line 2 = AMT (Form
  6251 line 11), line 3 = line 1z + line 2 → Form 1040 line 17.
  https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
- IRS Form 1040 instructions (line 17 = Schedule 2 line 3; line 23 =
  Schedule 2 line 21):
  https://www.irs.gov/instructions/i1040gi

B1 surfaces the Schedule 2 line-level decomposition as declared rule
outputs so the form-renderer reads each line through a real
``StageResult.output_fingerprint`` (invariants I2 / I11) and the prior
projection-side ``schedule2_line21 = schedule2_line1_amt + schedule2_line12``
arithmetic is removed (invariant I5). The declared outputs are:

  - ``us.tax.schedule_2_line_1_amt_usd``                       (US25-AMT-FTC-AND-COMPARE) — 2025 IRS line 2 (key name retained for fingerprint stability)
  - ``us.tax.schedule_2_line_3_total_amt_usd``                 (US25-21-PAYMENTS)
  - ``us.tax.schedule_2_line_4_se_tax_usd``                    (US25-SE-TAX)
  - ``us.tax.schedule_2_line_11_additional_medicare_usd``      (US25-ADDITIONAL-MEDICARE)
  - ``us.tax.schedule_2_line_12_niit_usd``                     (US25-20-NIIT)
  - ``us.tax.schedule_2_line_21_total_other_taxes_usd``        (US25-21-PAYMENTS)
"""
from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_rules import (
    execute_us_rule_graph,
    us_initial_facts_2025,
    us_initial_fingerprints_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


D = Decimal


class Schedule2LineDeclarationTest(unittest.TestCase):
    """The producing stages must declare the new ``us.tax.schedule_2_*``
    outputs in their ``output_keys`` (and therefore in
    ``OutputDeclaration``).
    """

    def setUp(self) -> None:
        self.stages = {s.stage_id: s for s in usa_law_stages_2025()}

    def test_each_schedule_2_line_is_declared_by_its_producing_stage(self) -> None:
        # ``(stage_id, output_key)`` pairs the rendered Schedule 2 walk
        # depends on. A regression that drops any one of these breaks
        # the renderer's per-line read at the I3 boundary.
        expected = (
            ("US25-AMT-FTC-AND-COMPARE", "us.tax.schedule_2_line_1_amt_usd"),
            ("US25-SE-TAX", "us.tax.schedule_2_line_4_se_tax_usd"),
            (
                "US25-ADDITIONAL-MEDICARE",
                "us.tax.schedule_2_line_11_additional_medicare_usd",
            ),
            ("US25-20-NIIT", "us.tax.schedule_2_line_12_niit_usd"),
            ("US25-21-PAYMENTS", "us.tax.schedule_2_line_3_total_amt_usd"),
            (
                "US25-21-PAYMENTS",
                "us.tax.schedule_2_line_21_total_other_taxes_usd",
            ),
        )
        for stage_id, output_key in expected:
            with self.subTest(stage=stage_id, output_key=output_key):
                self.assertIn(output_key, self.stages[stage_id].output_keys)

    def test_each_line_has_form_line_ref_to_schedule_2(self) -> None:
        # I3 (bidirectional): every Schedule 2 line we surface as a rule
        # output must carry a FormLineRef the renderer reads.
        # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line 2 = AMT per
        # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf. The output key
        # ``us.tax.schedule_2_line_1_amt_usd`` retains 2024 line numbering
        # for fingerprint stability; the FormLineRef.line value below is
        # the authoritative 2025 IRS line number ("2").
        wanted = {
            "us.tax.schedule_2_line_1_amt_usd": "2",
            "us.tax.schedule_2_line_3_total_amt_usd": "3",
            "us.tax.schedule_2_line_4_se_tax_usd": "4",
            "us.tax.schedule_2_line_11_additional_medicare_usd": "11",
            "us.tax.schedule_2_line_12_niit_usd": "12",
            "us.tax.schedule_2_line_21_total_other_taxes_usd": "21",
        }
        seen: dict[str, str] = {}
        for stage in self.stages.values():
            for declaration in stage.outputs:
                if declaration.key in wanted:
                    forms = {
                        (ref.form, ref.line) for ref in declaration.form_line_refs
                    }
                    seen[declaration.key] = ""
                    self.assertIn(
                        ("Schedule 2", wanted[declaration.key]),
                        forms,
                        f"{declaration.key} must declare FormLineRef(form='Schedule 2', "
                        f"line='{wanted[declaration.key]}')",
                    )
        self.assertEqual(set(seen), set(wanted))


class Schedule2LineValuesTest(unittest.TestCase):
    """Executed rule graph must materialize the new keys and the values
    must satisfy the Schedule 2 line semantics."""

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
        initial_facts = us_initial_facts_2025(inputs)
        execution = execute_us_rule_graph(
            initial_facts,
            input_fingerprints=us_initial_fingerprints_2025(initial_facts),
        )
        return execution

    def test_executor_materializes_all_six_keys(self) -> None:
        execution = self._executed_facts()
        for key in (
            "us.tax.schedule_2_line_1_amt_usd",
            "us.tax.schedule_2_line_3_total_amt_usd",
            "us.tax.schedule_2_line_4_se_tax_usd",
            "us.tax.schedule_2_line_11_additional_medicare_usd",
            "us.tax.schedule_2_line_12_niit_usd",
            "us.tax.schedule_2_line_21_total_other_taxes_usd",
        ):
            self.assertIn(key, execution.final_facts)

    def test_line_1_equals_treaty_resourced_amt_owed(self) -> None:
        # B1: Schedule 2 line 2 (2025 revision; was line 1 on 2024
        # revision) is the chosen treaty-resourcing AMT
        # (``amt_owed.amt_owed_usd``), not the no-treaty AMT. The
        # output key name retains 2024 line numbering for fingerprint
        # stability.
        execution = self._executed_facts()
        amt_owed = execution.final_facts["us.stage.amt_owed"]
        self.assertEqual(
            execution.final_facts["us.tax.schedule_2_line_1_amt_usd"],
            amt_owed["amt_owed_usd"],
        )

    def test_line_3_equals_line_1_in_supported_posture(self) -> None:
        # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025): line 3 = line 1z
        # + line 2 (AMT). In the supported posture line 1z (additions to
        # tax: APTC, clean-vehicle credit repayments, Form 4255 EPE
        # recapture, other) = $0, so line 3 = line 2 (AMT). The internal
        # output key ``us.tax.schedule_2_line_1_amt_usd`` retains the
        # 2024 line-1 name for fingerprint stability — the value is the
        # AMT scalar regardless of which IRS line carries it.
        execution = self._executed_facts()
        self.assertEqual(
            execution.final_facts["us.tax.schedule_2_line_3_total_amt_usd"],
            execution.final_facts["us.tax.schedule_2_line_1_amt_usd"],
        )

    def test_line_4_equals_se_tax_scalar(self) -> None:
        execution = self._executed_facts()
        se = execution.final_facts["us.stage.se_tax"]
        self.assertEqual(
            execution.final_facts["us.tax.schedule_2_line_4_se_tax_usd"],
            se["se_tax_usd"],
        )

    def test_line_11_equals_additional_medicare_scalar(self) -> None:
        execution = self._executed_facts()
        am = execution.final_facts["us.stage.additional_medicare"]
        self.assertEqual(
            execution.final_facts[
                "us.tax.schedule_2_line_11_additional_medicare_usd"
            ],
            am["additional_medicare_tax_usd"],
        )

    def test_line_12_equals_niit_scalar(self) -> None:
        execution = self._executed_facts()
        niit = execution.final_facts["us.stage.niit"]
        self.assertEqual(
            execution.final_facts["us.tax.schedule_2_line_12_niit_usd"],
            niit["niit_usd"],
        )

    def test_line_21_equals_sum_of_lines_4_11_12(self) -> None:
        # Line 21 = SE tax + Additional Medicare + NIIT for the supported
        # posture (no other Part II taxes modeled).
        execution = self._executed_facts()
        line_4 = execution.final_facts["us.tax.schedule_2_line_4_se_tax_usd"]
        line_11 = execution.final_facts[
            "us.tax.schedule_2_line_11_additional_medicare_usd"
        ]
        line_12 = execution.final_facts["us.tax.schedule_2_line_12_niit_usd"]
        expected = (line_4 + line_11 + line_12).quantize(D("0.01"))
        self.assertEqual(
            execution.final_facts[
                "us.tax.schedule_2_line_21_total_other_taxes_usd"
            ],
            expected,
        )


class Schedule2RendererEmitsLinesTest(unittest.TestCase):
    """Renderer-side: ``_write_schedule_2`` must emit a markdown row for
    every declared Schedule 2 line. The test reads the actual generated
    markdown to confirm the renderer wired up correctly.
    """

    def test_renderer_emits_all_schedule_2_lines(self) -> None:
        from tax_pipeline.run_year import run_year

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            run_year(Path(tmp), "2025", workspace_root=paths.year_root)
            schedule_2_md = (
                paths.usa_forms_root / f"{paths.year}_schedule_2.md"
            ).read_text(encoding="utf-8")

        # Each line label must appear in the rendered markdown.
        # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025 revision) Part I
        # AMT row is line 2, not line 1. https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
        for label in ("Line 2", "Line 3", "Line 4", "Line 11", "Line 12", "Line 21"):
            self.assertIn(label, schedule_2_md)
        # Authority cite must appear.
        self.assertIn(
            "https://www.irs.gov/pub/irs-pdf/f1040s2.pdf",
            schedule_2_md,
        )


if __name__ == "__main__":
    unittest.main()
