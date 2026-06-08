from __future__ import annotations

import inspect
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_law import compute_us_assessment_2025
from tax_pipeline.y2025.us_stages import usa_law_stages_2025
from tax_pipeline.y2025.us_rules import (
    execute_us_rule_graph,
    us_initial_facts_2025,
    us_initial_fingerprints_2025,
)
from tax_pipeline.y2025.treaty_rules import (
    execute_treaty_rule_graph,
    treaty_initial_facts_2025,
    treaty_initial_fingerprints_2025,
)
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.core.stages import LawStage, validate_law_stage_graph


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _initial_fingerprints_for(stages: tuple[LawStage, ...]) -> dict[str, str]:
    output_keys = {key for stage in stages for key in stage.output_keys}
    input_keys: set[str] = set()
    for stage in stages:
        input_keys.update(stage.input_fact_keys)
    initial_keys = input_keys - output_keys
    return {key: f"sha256:{key}" for key in sorted(initial_keys)}


class USA2025StagesTest(unittest.TestCase):
    def _load_demo_inputs_with_germany_packet(self, paths):
        return load_us_assessment_inputs_2025(
            paths,
            germany_treaty_dividend_items=(
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

    def test_usa_stage_graph_declares_irc_1_61_63_901_904_1411_order(self) -> None:
        # The U.S. sequence must make AGI under section 61, taxable income under
        # section 63, tax under section 1, FTC under sections 901/904, and NIIT
        # under section 1411 auditable before any renderer writes a form surface.
        # IRS Publication 514 treaty re-sourcing worksheet line 21 is entered on
        # Form 1116 line 12 before final FTC/payment presentation, so the treaty
        # credit stage must precede the final allowed-FTC stage.
        stages = usa_law_stages_2025()

        self.assertEqual(stages[0].stage_id, "US25-00-FILING-POSITION")
        # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03) appended
        # ``US25-FATCA-FBAR-DETERMINATION`` after ``US25-21-PAYMENTS``
        # because the FATCA / FBAR determination is independent of tax
        # owed (it does not feed any downstream tax stage). The
        # ``US25-21-PAYMENTS`` stage remains the last tax-affecting
        # stage, but the FATCA / FBAR determination stage is the last
        # stage in the executed graph since it carries the same posture
        # forward to the renderer's status sheets.
        stage_ids = [stage.stage_id for stage in stages]
        self.assertLess(
            stage_ids.index("US25-21-PAYMENTS"),
            stage_ids.index("US25-FATCA-FBAR-DETERMINATION"),
        )
        self.assertEqual(stages[-1].stage_id, "US25-FATCA-FBAR-DETERMINATION")
        refs = {stage.stage_id: " ".join(stage.legal_refs) for stage in stages}
        self.assertIn("26 U.S.C. § 61", refs["US25-07-AGI"])
        self.assertIn("26 U.S.C. § 63", refs["US25-08-TAXABLE-INCOME"])
        self.assertIn("26 U.S.C. § 1", refs["US25-09-REGULAR-TAX"])
        self.assertIn("26 U.S.C. §§ 901 and 904", refs["US25-19-ALLOWED-FTC"])
        self.assertIn("26 U.S.C. § 1411", refs["US25-20-NIIT"])
        # Stages[6] is the § 1(h) preferential capital base; stages[7] used to
        # be US25-07-AGI but F-C1 inserted US25-SE-TAX immediately ahead of
        # AGI so the § 164(f) one-half SE-tax deduction can flow into AGI.
        # Look up the stage by id instead of pinning a brittle list index.
        stages_by_id = {stage.stage_id: stage for stage in stages}
        self.assertIn("us.stage.capital_buckets", stages[6].input_fact_keys)
        self.assertIn("us.stage.section_1256_split", stages[6].input_fact_keys)
        self.assertIn(
            "us.stage.capital_loss_result",
            stages_by_id["US25-07-AGI"].input_fact_keys,
        )
        # F-C1 — US25-07-AGI now reads us.stage.se_tax to apply 26 U.S.C.
        # § 164(f)(1) one-half SE-tax above-the-line deduction.
        self.assertIn(
            "us.stage.se_tax",
            stages_by_id["US25-07-AGI"].input_fact_keys,
        )
        # US25-SE-TAX must precede US25-07-AGI per F-C1.
        self.assertLess(
            stage_ids.index("US25-SE-TAX"), stage_ids.index("US25-07-AGI")
        )
        self.assertLess(stage_ids.index("US25-18-TREATY-ADDITIONAL-FTC"), stage_ids.index("US25-19-ALLOWED-FTC"))
        validate_law_stage_graph(stages, available_fact_keys=set(_initial_fingerprints_for(stages)))

        with self.assertRaisesRegex(ValueError, "missing input"):
            validate_law_stage_graph(
                tuple(reversed(stages)),
                available_fact_keys=set(_initial_fingerprints_for(stages)),
            )

    def test_usa_stage_graph_executes_through_real_per_stage_calculate_functions(self) -> None:
        # Phase 4 of the engine restructure: US25-00 through US25-21 must execute
        # through real ``LawRule.calculate`` functions (no replay, no lookup-
        # lambda). The executed StageResults are the audit-graph source of
        # truth, not a projection of pre-computed Assessment values.
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            inputs = self._load_demo_inputs_with_germany_packet(paths)
            assessment = compute_us_assessment_2025(inputs)

        stages = usa_law_stages_2025()
        initial_facts = us_initial_facts_2025(inputs)
        execution = execute_us_rule_graph(
            initial_facts,
            input_fingerprints=us_initial_fingerprints_2025(initial_facts),
        )

        self.assertEqual(
            [result.stage_id for result in execution.stage_results],
            [stage.stage_id for stage in stages],
        )
        self.assertTrue(all(result.precision_notes for result in execution.stage_results))
        outputs_by_stage = {result.stage_id: result.outputs for result in execution.stage_results}
        self.assertEqual(
            outputs_by_stage["US25-04-SECTION-1256"]["us.stage.section_1256_split"]["total_usd"],
            assessment.capital.section_1256_total_usd,
        )
        self.assertEqual(
            outputs_by_stage["US25-05-CAPITAL-LOSS-LINE-7A"]["us.stage.capital_loss_result"]["form_1040_line_7a_usd"],
            assessment.capital.form_1040_line_7a_usd,
        )
        self.assertEqual(
            outputs_by_stage["US25-19-ALLOWED-FTC"]["us.stage.allowed_ftc"]["total_allowed_ftc_after_treaty_resourcing_usd"],
            assessment.ftc.total_allowed_ftc_usd
            + assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd,
        )
        # Executed StageResults must validate against the declared graph: every
        # declared output produced, every input fingerprint resolved.
        validate_law_stage_graph(
            stages,
            available_fact_keys=set(initial_facts.keys()),
            stage_results=execution.stage_results,
        )

    def test_treaty_stage_graph_executes_through_real_per_stage_calculate_functions(self) -> None:
        # Phase 1 of the engine restructure: TREATY25-15 through TREATY25-18 must
        # execute through real ``LawRule.calculate`` functions (no replay, no
        # lookup-lambda). The executed StageResults are the audit-graph source of
        # truth, not a projection of pre-computed Assessment values.
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            inputs = self._load_demo_inputs_with_germany_packet(paths)
            assessment = compute_us_assessment_2025(inputs)

        stages = treaty_law_stages_2025()
        # Build initial facts the same way ``treaty_resourcing_assessment_2025``
        # does internally, and run the rule graph end-to-end.
        ftc_assessment = assessment.ftc
        regular = assessment.regular_tax
        initial_facts = treaty_initial_facts_2025(
            treaty_inputs=inputs.treaty_inputs,
            ordinary_dividends_usd=inputs.capital_facts.ordinary_dividends_usd,
            qualified_dividends_usd=inputs.capital_facts.qualified_dividends_usd,
            foreign_source_passive_dividends_usd=inputs.ftc_inputs.foreign_source_passive_dividends_usd,
            foreign_source_qualified_dividends_usd=inputs.ftc_inputs.foreign_source_qualified_dividends_usd,
            regular_tax_before_credits_usd=regular.regular_tax_before_credits_usd,
            taxable_income_usd=regular.taxable_income_usd,
            regular_tax_after_ftc_usd=ftc_assessment.regular_tax_after_ftc_usd,
            remaining_form_1116_line_33_cap_usd=max(
                Decimal("0.00"),
                regular.regular_tax_before_credits_usd - ftc_assessment.total_allowed_ftc_usd,
            ),
        )
        execution = execute_treaty_rule_graph(
            initial_facts,
            input_fingerprints=treaty_initial_fingerprints_2025(initial_facts),
        )

        # Workstream 4 — DBA-USA Art. 28 LOB qualification gate now
        # heads the treaty graph; the Pub. 514 worksheet starts at
        # TREATY25-15.
        self.assertEqual(stages[0].stage_id, "TREATY25-LOB-QUALIFICATION")
        self.assertEqual(stages[1].stage_id, "TREATY25-15-US-SOURCE-DIVIDENDS")
        self.assertEqual(stages[-1].stage_id, "TREATY25-18-ADDITIONAL-FTC")
        # Every Pub. 514 worksheet stage cites Pub. 514 / Germany treaty;
        # the LOB head stage cites Art. 28 instead.
        for stage in stages[1:]:
            self.assertTrue(
                "Publication 514" in " ".join(stage.legal_refs)
                or "Germany treaty" in " ".join(stage.legal_refs)
            )
        self.assertEqual(
            [result.stage_id for result in execution.stage_results],
            [stage.stage_id for stage in stages],
        )
        # The executed StageResults must validate against the declared graph: every
        # declared output key produced, every input fingerprint resolved.
        validate_law_stage_graph(
            stages,
            available_fact_keys=set(initial_facts.keys()),
            stage_results=execution.stage_results,
        )
        # Sanity: the graph's final additional-FTC matches the legacy assessment view.
        self.assertEqual(
            execution.final_facts["treaty.additional_foreign_tax_credit"],
            assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd,
        )

    def test_us_stage_modules_are_pure_adapters_without_file_io(self) -> None:
        import tax_pipeline.y2025.treaty_stages as treaty_stages
        import tax_pipeline.y2025.us_stages as usa_stages

        for module in (usa_stages, treaty_stages):
            source = inspect.getsource(module)
            for token in ("Path(", "open(", "read_text(", "write_text(", "read_bytes(", "write_bytes("):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
