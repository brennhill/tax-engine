"""US25-21-PAYMENTS — Form 1040 line 22 (tax after nonrefundable credits) (A2).

Authority:
- Form 1040 instructions (2025) — line 22 = max(0, line 18 minus line 21).
  https://www.irs.gov/instructions/i1040gi
- 26 U.S.C. § 24(b)(3) — CTC nonrefundable credit ordered before additional
  taxes on Schedule 2.
- 26 U.S.C. § 901 / § 904 — FTC nonrefundable, on Schedule 3 line 1 / Form
  1040 line 20.

A2 of FORM-MAPPING-FOLLOWUP.md added two declared rule outputs to the
US25-21-PAYMENTS stage:

  - ``us.tax.line_22_after_credits_usd``                       (no-treaty baseline)
  - ``us.tax.line_22_after_credits_with_treaty_resourcing_usd`` (treaty posture)

so the rendered 1040 walks 16 / 17 / 19 / 20 / 22 / 23 instead of jumping
from 21 to 23. The subtraction lives inside ``us25_21_payments.calculate``
per invariant I5 (no Decimal arithmetic on legal output keys outside the
rule graph). This file is the regression battery covering:

  (a) the rule's ``output_keys`` declaration includes both line-22 keys;
  (b) the executor materializes both keys at execution time;
  (c) the values match the line-18 minus line-21 statutory subtraction
      under a posture with non-zero baseline FTC + non-zero treaty
      additional FTC (the demo workspace + a non-zero treaty packet).
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


class US25Form1040Line22Test(unittest.TestCase):
    """A2 — Form 1040 line 22 must be a declared rule output produced by
    US25-21-PAYMENTS, not a renderer-side subtraction.
    """

    def _executed_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            write_demo_us_treaty_dividend_items(paths)
            inputs = load_us_assessment_inputs_2025(
                paths,
                germany_treaty_dividend_items=(
                    # Non-zero treaty additional FTC posture so line_21 with
                    # treaty re-sourcing is strictly greater than the baseline.
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

    def test_us25_21_declares_both_line_22_outputs(self) -> None:
        # I8: the rule's output_keys must include both line-22 keys so the
        # executor's ``validate_result`` accepts the per-rule dict with both
        # entries (and rejects any future regression that drops them).
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        stage = stages["US25-21-PAYMENTS"]
        self.assertIn("us.tax.line_22_after_credits_usd", stage.output_keys)
        self.assertIn(
            "us.tax.line_22_after_credits_with_treaty_resourcing_usd",
            stage.output_keys,
        )

    def test_us25_21_authority_cites_form_1040_line_22(self) -> None:
        # A2 cites Form 1040 instructions and 26 U.S.C. § 24(b)(3) ordering;
        # the legal_refs string must carry both authorities so the audit
        # packet names them.
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        stage = stages["US25-21-PAYMENTS"]
        joined = " ".join(stage.legal_refs)
        self.assertIn("Instructions for Form 1040", joined)
        self.assertIn("26 U.S.C. § 24", joined)

    def test_executed_facts_contain_both_line_22_keys(self) -> None:
        # The executor must materialize both keys at the top level of
        # ``execution.final_facts`` so ``us_model.py`` can project them onto
        # ``tax.line_22_after_credits_*`` in ``us-tax-estimate.json``.
        execution = self._executed_facts()
        self.assertIn("us.tax.line_22_after_credits_usd", execution.final_facts)
        self.assertIn(
            "us.tax.line_22_after_credits_with_treaty_resourcing_usd",
            execution.final_facts,
        )

    def test_line_22_baseline_equals_line_18_minus_line_21(self) -> None:
        # Form 1040 instructions: line 22 = max(0, line 18 − line 21), where
        #   line 18 = line 16 (regular tax) + line 17 (Schedule 2 line 3 — AMT)
        #   line 21 = line 19 (CTC nonrefundable) + line 20 (Schedule 3 total)
        # The no-treaty baseline uses ``amt_owed_without_treaty_resourcing_usd``
        # for line 17 and the baseline-only allowed FTC for the Schedule 3
        # total. (For the demo, AMT = $0 and CTC nonrefundable = $0, so the
        # subtraction reduces to ``regular_tax − baseline_total_allowed_ftc``.)
        execution = self._executed_facts()
        outputs_by_stage = {r.stage_id: r.outputs for r in execution.stage_results}
        regular_tax = outputs_by_stage["US25-09-REGULAR-TAX"][
            "us.stage.regular_tax_before_credits"
        ]["regular_tax_before_credits_usd"]
        amt_owed = outputs_by_stage["US25-AMT-FTC-AND-COMPARE"]["us.stage.amt_owed"]
        baseline = outputs_by_stage["US25-14-BASELINE-ALLOWED-FTC"][
            "us.stage.baseline_allowed_ftc"
        ]
        ctc_nonrefundable = outputs_by_stage["US25-CTC-AND-ODC"][
            "us.ctc.nonrefundable_portion_usd"
        ]
        line_18 = regular_tax + amt_owed["amt_owed_without_treaty_resourcing_usd"]
        line_21 = ctc_nonrefundable + baseline["total_allowed_ftc_usd"]
        expected_line_22 = max(D("0.00"), line_18 - line_21).quantize(D("0.01"))
        self.assertEqual(
            execution.final_facts["us.tax.line_22_after_credits_usd"],
            expected_line_22,
        )

    def test_line_22_treaty_includes_pub_514_additional_ftc(self) -> None:
        # In the treaty re-sourcing posture, line 20 (Schedule 3 total) =
        # baseline allowed FTC + Pub. 514 worksheet line 21 additional FTC,
        # so the treaty-posture line 22 is strictly less than (or equal to)
        # the baseline line 22 — the additional FTC reduces tax after credits.
        execution = self._executed_facts()
        outputs_by_stage = {r.stage_id: r.outputs for r in execution.stage_results}
        regular_tax = outputs_by_stage["US25-09-REGULAR-TAX"][
            "us.stage.regular_tax_before_credits"
        ]["regular_tax_before_credits_usd"]
        amt_owed = outputs_by_stage["US25-AMT-FTC-AND-COMPARE"]["us.stage.amt_owed"]
        baseline = outputs_by_stage["US25-14-BASELINE-ALLOWED-FTC"][
            "us.stage.baseline_allowed_ftc"
        ]
        treaty_additional = outputs_by_stage["US25-18-TREATY-ADDITIONAL-FTC"][
            "us.stage.treaty_additional_ftc"
        ]
        ctc_nonrefundable = outputs_by_stage["US25-CTC-AND-ODC"][
            "us.ctc.nonrefundable_portion_usd"
        ]
        line_18_with_treaty = (
            regular_tax + amt_owed["amt_owed_usd"]
        )
        treaty_ftc_total = (
            baseline["total_allowed_ftc_usd"]
            + treaty_additional["treaty_resourcing_additional_ftc_usd"]
        ).quantize(D("0.01"))
        line_21_with_treaty = (ctc_nonrefundable + treaty_ftc_total).quantize(D("0.01"))
        expected_line_22 = max(D("0.00"), line_18_with_treaty - line_21_with_treaty).quantize(
            D("0.01")
        )
        self.assertEqual(
            execution.final_facts[
                "us.tax.line_22_after_credits_with_treaty_resourcing_usd"
            ],
            expected_line_22,
        )

    def test_line_22_floored_at_zero(self) -> None:
        # Form 1040 instructions: line 22 is "If zero or less, enter -0-".
        # Both versions must therefore satisfy ``value >= 0`` regardless of
        # posture.
        execution = self._executed_facts()
        self.assertGreaterEqual(
            execution.final_facts["us.tax.line_22_after_credits_usd"], D("0.00")
        )
        self.assertGreaterEqual(
            execution.final_facts[
                "us.tax.line_22_after_credits_with_treaty_resourcing_usd"
            ],
            D("0.00"),
        )


if __name__ == "__main__":
    unittest.main()
