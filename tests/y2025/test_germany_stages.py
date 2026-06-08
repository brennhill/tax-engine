from __future__ import annotations

from dataclasses import is_dataclass
from decimal import Decimal
import inspect
import unittest

from tax_pipeline.y2025.germany_law import (
    GermanyCapitalAssessmentInputs2025,
)
from tax_pipeline.y2025.germany_stages import (
    germany_capital_law_stages_2025,
    germany_law_stages_2025,
    germany_ordinary_law_stages_2025,
)
from tax_pipeline.y2025.germany_capital_rules import (
    execute_germany_capital_rule_graph,
    germany_capital_initial_facts_2025,
    germany_capital_initial_fingerprints_2025,
)
from tax_pipeline.core.stages import LawStage, validate_law_stage_graph
from tests._germany_derived_facts import germany_derived_facts_for_inputs


def _initial_fingerprints_for(stages: tuple[LawStage, ...]) -> dict[str, str]:
    output_keys = {key for stage in stages for key in stage.output_keys}
    input_keys: set[str] = set()
    for stage in stages:
        input_keys.update(stage.input_fact_keys)
    initial_keys = input_keys - output_keys
    return {key: f"sha256:{key}" for key in sorted(initial_keys)}


class Germany2025StagesTest(unittest.TestCase):
    def test_germany_ordinary_stage_graph_is_one_canonical_list_with_posture_inputs(self) -> None:
        # Phase 3: filing posture is an input fact, not a rule-list branch. The
        # 12 ordinary stages are declared once; posture-driven legal branches
        # (joint vs basic tariff, joint Pauschbetrag vs single Pauschbetrag,
        # § 26 vs § 26a vs single gate) live inside the per-stage calculate
        # bodies. The consolidated stage's legal_refs cite all branches'
        # authorities so the audit trail does not lose the law citations.
        stages = germany_ordinary_law_stages_2025()

        self.assertEqual(
            [stage.stage_id for stage in stages],
            [
                "DE25-00-FILING-POSTURE-GATE",
                "DE25-01-WAGE-INCOME",
                "DE25-02-WERBUNGSKOSTEN",
                "DE25-03-NET-EMPLOYMENT",
                "DE25-04-OTHER-22NR3",
                "DE25-ALTERSENTLASTUNGSBETRAG",
                "DE25-ARBEITSZIMMER",
                "DE25-05-RETIREMENT-SA",
                "DE25-06-HEALTH-VORSORGE-SA",
                "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
                "DE25-SPENDENABZUG",
                "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
                "DE25-UNTERHALTSLEISTUNGEN",
                "DE25-BEHINDERUNG-PAUSCHBETRAG",
                "DE25-07-TAXABLE-INCOME",
                "DE25-08-INCOME-TAX-TARIFF",
                "DE25-09-ORDINARY-SOLI",
                "DE25-10-ORDINARY-CREDITS",
            ],
        )
        self.assertTrue(all(stage.legal_refs for stage in stages))
        self.assertTrue(all(stage.authority_urls for stage in stages))
        # Filing-posture gate cites every posture's authority section.
        gate_refs = " ".join(stages[0].legal_refs)
        self.assertIn("§ 26 EStG", gate_refs)
        self.assertIn("§ 26a EStG", gate_refs)
        self.assertIn("§ 26b EStG", gate_refs)
        # Tariff stage cites both § 32a Abs. 1 and § 32a Abs. 5 because the
        # branch is selected at run time by the input filing_posture.
        tariff_refs = " ".join(stages[15].legal_refs)
        self.assertIn("§ 32a Abs. 1 EStG", tariff_refs)
        self.assertIn("§ 32a Abs. 5 EStG", tariff_refs)
        self.assertIn("§ 26b EStG", tariff_refs)
        # Sonderausgaben stage continues to cite § 10c.
        self.assertIn("§ 10c EStG", stages[9].legal_refs)
        # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): DE25-06B exposes a
        # second declared scalar output for the § 10c Pauschbetrag amount
        # so the Anlage Sonderausgaben renderer reads a fingerprinted
        # Decimal directly via I11.
        self.assertEqual(
            stages[9].output_keys,
            (
                "de.ordinary.total_special_expenses",
                "de.ordinary.sonderausgaben_pauschbetrag_applied_eur",
            ),
        )
        validate_law_stage_graph(
            stages,
            available_fact_keys=set(_initial_fingerprints_for(stages)),
        )

    def test_germany_capital_stage_graph_declares_section_20_to_32d_order(self) -> None:
        # Section 20 EStG buckets must precede InvStG partial exemption, section 20(6)
        # netting, section 20(9) saver allowance, section 32d tax/credit, then SolzG.
        stages = germany_capital_law_stages_2025()

        self.assertEqual(stages[0].stage_id, "DE25-13-CAPITAL-RAW-BUCKETS")
        self.assertEqual(stages[-1].stage_id, "DE25-21-FINAL-CAPITAL-TAX")
        self.assertEqual(stages[-1].output_keys, ("de.capital.final_tax",))
        stage_ids = [stage.stage_id for stage in stages]
        refs = {stage.stage_id: " ".join(stage.legal_refs) for stage in stages}
        # § 32d Abs. 1 EStG imposes gross flat tax first, § 32d Abs. 5 then
        # reduces that tax by creditable foreign tax, and § 4 SolzG applies to
        # the remaining assessed capital income tax.
        self.assertLess(stage_ids.index("DE25-17-SECTION-32D1-GROSS-TAX"), stage_ids.index("DE25-18-SECTION-32D5-FTC"))
        self.assertLess(stage_ids.index("DE25-18-SECTION-32D5-FTC"), stage_ids.index("DE25-19-CAPITAL-SOLI"))
        # InvStG § 19 Vorabpauschale (laufender Ertrag) is part of § 20 Abs. 6
        # EStG's non-stock-net bucket; the stage must run before DE25-15 so
        # the deemed-distribution amount enters the netting. Authority:
        # https://www.gesetze-im-internet.de/invstg_2018/__19.html
        self.assertLess(
            stage_ids.index("DE25-13F-VORABPAUSCHALE"),
            stage_ids.index("DE25-15-SECTION-20-6-NETTING"),
        )
        self.assertIn("§ 20 Abs. 6", refs["DE25-15-SECTION-20-6-NETTING"])
        # DE25-16 is the saver-allowance stage and follows DE25-15.
        # A4 (FORM-MAPPING-FOLLOWUP) added
        # ``de.capital.sparer_pauschbetrag_claimed_eur`` (Anlage KAP
        # Zeile 4) alongside the existing ``taxable_after_allowance``
        # (Anlage KAP Zeile 17) output.
        de25_16_index = stage_ids.index("DE25-16-SECTION-20-9-SAVER")
        self.assertEqual(
            stages[de25_16_index].output_keys,
            (
                "de.capital.taxable_after_allowance",
                "de.capital.sparer_pauschbetrag_claimed_eur",
            ),
        )
        self.assertIn(
            "de.capital.taxable_after_allowance",
            stages[de25_16_index + 1].input_fact_keys,
        )
        self.assertIn("§ 32d Abs. 1", refs["DE25-17-SECTION-32D1-GROSS-TAX"])
        self.assertIn("§ 32d Abs. 5", refs["DE25-18-SECTION-32D5-FTC"])
        self.assertIn("§ 3 SolzG", refs["DE25-19-CAPITAL-SOLI"])
        self.assertIn("§ 4 SolzG", refs["DE25-19-CAPITAL-SOLI"])
        validate_law_stage_graph(
            stages,
            available_fact_keys=set(_initial_fingerprints_for(stages)),
        )

        with self.assertRaisesRegex(ValueError, "missing input"):
            validate_law_stage_graph(
                tuple(reversed(stages)),
                available_fact_keys=set(_initial_fingerprints_for(stages)),
            )

    def test_germany_ordinary_stage_graph_carries_section_36_rounding_policy(self) -> None:
        # The full per-stage rule-graph execution path is exercised end-to-end in
        # test_germany_2025_law.py (golden-number tests) and in
        # tests/test_year_pipeline.py. This test verifies the static LawStage
        # declarations still carry the § 36 Abs. 3 EStG rounding policy that the
        # rule-graph wrapper relies on.
        ordinary_stages = germany_ordinary_law_stages_2025()
        ordinary_credit_stage = next(stage for stage in ordinary_stages if stage.stage_id == "DE25-10-ORDINARY-CREDITS")
        self.assertIn("§ 36 Abs. 3", ordinary_credit_stage.rounding_policy)
        self.assertIn("prepayments remain exact", ordinary_credit_stage.rounding_policy)

    def test_germany_capital_stage_graph_executes_through_real_per_stage_calculate_functions(self) -> None:
        # Phase 2 of the engine restructure: DE25-13 through DE25-21 must execute
        # through real ``LawRule.calculate`` functions (no replay, no lookup-
        # lambda). The executed StageResults are the audit-graph source of truth,
        # not a projection of pre-computed Assessment values. End-to-end capital
        # math (with real fund classification, foreign tax credit ordering, etc.)
        # is exercised in test_germany_2025_law.py; here we verify the rule graph
        # validates against the declared LawStage contract on a minimal input.
        capital_stages = germany_capital_law_stages_2025()
        inputs = GermanyCapitalAssessmentInputs2025(
            sale_facts=(),
            income_facts=(),
            dher_stock_gain_eur=Decimal("0.00"),
            stock_loss_carryforward_2024_eur=Decimal("0.00"),
            saver_allowance_eur=Decimal("2000.00"),
            capital_tax_rate=Decimal("0.25"),
            soli_rate=Decimal("0.055"),
            treaty_dividend_credit_eur=Decimal("0.00"),
            fund_classification={},
        )
        # F-A4: ``germany_capital_initial_facts_2025`` reads ``de.derived.*``
        # from ``derived-facts.json`` on disk in production. Tests that
        # bypass ``run_year`` materialize the boundary state via the
        # canonical Pipeline 1 derivation graph (see
        # ``tests/_germany_derived_facts.py``).
        initial_facts = germany_capital_initial_facts_2025(
            inputs,
            derived_facts=germany_derived_facts_for_inputs(inputs),
        )
        execution = execute_germany_capital_rule_graph(
            initial_facts,
            input_fingerprints=germany_capital_initial_fingerprints_2025(initial_facts),
        )
        self.assertEqual(
            [result.stage_id for result in execution.stage_results],
            [stage.stage_id for stage in capital_stages],
        )
        self.assertTrue(all(result.precision_notes for result in execution.stage_results))
        # The executed StageResults must validate against the declared graph: every
        # declared output key produced, every input fingerprint resolved.
        validate_law_stage_graph(
            capital_stages,
            available_fact_keys=set(initial_facts.keys()),
            stage_results=execution.stage_results,
        )
        # On an empty-input fixture the legal sequence still produces structured
        # zero outputs - no implicit zeros, every value comes from a calculate.
        self.assertEqual(execution.final_facts["de.capital.final_tax"], Decimal("0.00"))

    def test_germany_stage_module_is_pure_adapter_without_file_io(self) -> None:
        import tax_pipeline.y2025.germany_stages as stages

        self.assertTrue(is_dataclass(germany_law_stages_2025()[0]))
        source = inspect.getsource(stages)
        for token in ("Path(", "open(", "read_text(", "write_text(", "read_bytes(", "write_bytes("):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
