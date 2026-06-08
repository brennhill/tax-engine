"""US25-19A — final allowed FTC after Pub. 514 treaty re-sourcing.

Authority:
- 26 U.S.C. § 901 (foreign tax credit) -- https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
- 26 U.S.C. § 904 (FTC limitation) -- https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
- IRS Publication 514 (Pub. 514 worksheet line 21 → Form 1116 line 12) -- https://www.irs.gov/publications/p514
- DBA-USA Art. 23 (residence-country credit reconciliation)

This stage exists to keep the post-treaty allowed-FTC sum inside the rule
graph (LEAK-4 / I5 fix). Before this stage existed, ``us_model.py`` summed
``assessment.ftc.total_allowed_ftc_usd +
assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd`` at the
orchestrator boundary, which leaked legal math out of the audit graph.

Acceptance:
- Stage executes through ``execute_us_rule_graph`` and produces
  ``us.stage.total_allowed_ftc_after_treaty_resourcing_usd`` whose scalar
  equals ``baseline + treaty_additional`` (cent-rounded).
- The I5 invariant (``test_no_decimal_arithmetic_on_rule_outputs_in_orchestrators``)
  no longer flags ``us_model.py:170-173``.
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


class US25_19A_AllowedFTCAfterResourcingTest(unittest.TestCase):
    """The post-treaty allowed-FTC sum must be produced by US25-19A inside
    the rule graph, not recomputed by the orchestrator.
    """

    def _executed_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            inputs = load_us_assessment_inputs_2025(
                paths,
                germany_treaty_dividend_items=(
                    # A non-zero treaty add-on so the sum exercises both terms.
                    # Authority: DBA-USA Art. 10 + Pub. 514 worksheet line 21.
                    GermanyUSTreatyDividendPacketItem2025(
                        item_id="msft_us_dividend",
                        owner_slot="person_1",
                        dividend_class="portfolio_dividend",
                        gross_dividend_eur=Decimal("280.00"),
                        german_taxable_dividend_eur=Decimal("280.00"),
                        article_10_source_tax_ceiling_eur=Decimal("42.00"),
                        germany_precredit_tax_eur=Decimal("36.25"),
                        germany_residence_credit_eur=Decimal("36.25"),
                    ),
                ),
            )
        initial_facts = us_initial_facts_2025(inputs)
        execution = execute_us_rule_graph(
            initial_facts,
            input_fingerprints=us_initial_fingerprints_2025(initial_facts),
        )
        return execution

    def test_us25_19a_stage_is_declared_after_us25_19(self) -> None:
        # Stage ordering: the post-treaty sum must run after the baseline
        # allowed FTC (US25-19) and before payments (US25-21) so the
        # promoted fact-key is available when ``us_model.main`` reads it.
        stages = usa_law_stages_2025()
        ids = [s.stage_id for s in stages]
        self.assertIn("US25-19A-ALLOWED-FTC-AFTER-RESOURCING", ids)
        self.assertLess(ids.index("US25-19-ALLOWED-FTC"), ids.index("US25-19A-ALLOWED-FTC-AFTER-RESOURCING"))
        self.assertLess(ids.index("US25-19A-ALLOWED-FTC-AFTER-RESOURCING"), ids.index("US25-21-PAYMENTS"))

    def test_us25_19a_legal_refs_cite_901_904_pub514_treaty(self) -> None:
        # I0/CLAUDE.md: the controlling legal authorities for the post-treaty
        # allowed-FTC sum are IRC §§ 901 and 904 plus the Pub. 514 worksheet
        # line 21 / DBA-USA Art. 23 reconciliation.
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        stage = stages["US25-19A-ALLOWED-FTC-AFTER-RESOURCING"]
        joined = " ".join(stage.legal_refs)
        self.assertIn("26 U.S.C. § 901", joined)
        self.assertIn("26 U.S.C. § 904", joined)
        self.assertIn("Publication 514", joined)
        self.assertIn("DBA-USA", joined)
        self.assertTrue(stage.authority_urls, "must publish at least one authority URL")

    def test_us25_19a_sums_baseline_and_treaty_additional(self) -> None:
        # Pub. 514 worksheet: total allowed FTC after treaty re-sourcing =
        # baseline allowed FTC (§§ 901/904) + treaty additional FTC (worksheet
        # line 21, capped by Form 1116 line 33 remaining room).
        execution = self._executed_facts()
        outputs_by_stage = {r.stage_id: r.outputs for r in execution.stage_results}
        baseline = outputs_by_stage["US25-14-BASELINE-ALLOWED-FTC"]["us.stage.baseline_allowed_ftc"]
        treaty_additional = outputs_by_stage["US25-18-TREATY-ADDITIONAL-FTC"]["us.stage.treaty_additional_ftc"]
        promoted = outputs_by_stage["US25-19A-ALLOWED-FTC-AFTER-RESOURCING"][
            "us.stage.total_allowed_ftc_after_treaty_resourcing_usd"
        ]
        expected = (
            baseline["total_allowed_ftc_usd"]
            + treaty_additional["treaty_resourcing_additional_ftc_usd"]
        )
        # The promoted scalar (or scalar-in-dict) must equal the cent-rounded
        # baseline + treaty add-on.
        actual = (
            promoted["total_allowed_ftc_after_treaty_resourcing_usd"]
            if isinstance(promoted, dict)
            else promoted
        )
        self.assertEqual(actual, expected.quantize(Decimal("0.01")))

    def test_us25_19a_value_in_final_facts_for_orchestrator(self) -> None:
        # The orchestrator (us_model.main) must read this top-level fact key
        # instead of doing Decimal arithmetic on dataclass fields. This test
        # locks in the contract: the final-facts dict carries the promoted
        # value under the documented key.
        execution = self._executed_facts()
        self.assertIn(
            "us.stage.total_allowed_ftc_after_treaty_resourcing_usd",
            execution.final_facts,
        )

    def test_us_model_no_longer_sums_assessment_decimals(self) -> None:
        # I5 fix: the orchestrator must not re-derive the post-treaty allowed
        # FTC from ``assessment.ftc.total_allowed_ftc_usd +
        # assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd``.
        # Authority: CLAUDE.md "Renderers must not perform legal math".
        repo_root = Path(__file__).resolve().parents[2]
        source = (repo_root / "tax_pipeline" / "pipelines" / "y2025" / "us_model.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            "assessment.ftc.total_allowed_ftc_usd\n        + assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd",
            source,
        )


if __name__ == "__main__":
    unittest.main()
