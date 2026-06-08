"""TDD test for ``DE25-22-FINAL-REFUND`` (WS-4B).

The DE25-22 stage replaces the script-level headline-refund computation
at ``germany_model.py:317-335`` (flagged by I2 / I5 in
``docs/invariant-migration-plan.md``). Promoting the arithmetic into a
``LawRule.calculate`` body brings the headline number inside the audit
graph: ``StageResult`` fingerprints commit to the input components and
to ``de.final.target_refund_eur``, and the value appears in
``legal-execution-graph.json`` as a stage output.

Authority:
- § 36 Abs. 2 EStG (Anrechnung der Steuer / Erstattungsbetrag) — the
  final refund is income tax + soli credit balance after capital tax
  has been netted.
  https://www.gesetze-im-internet.de/estg/__36.html
- § 32d Abs. 1 EStG — the capital tax component being netted into the
  final refund. https://www.gesetze-im-internet.de/estg/__32d.html
- InvStG § 20 — the Teilfreistellung-aware capital tax that flows in.
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.core.stages import AuditWaypoint
from tax_pipeline.y2025.germany_stages import germany_law_stages_2025
from tax_pipeline.y2025.germany_final_rules import (
    de25_22_final_refund,
    execute_germany_final_rule_graph,
    germany_final_initial_facts_2025,
    germany_final_initial_fingerprints_2025,
)


D = Decimal


class De25_22FinalRefundTest(unittest.TestCase):
    """Per CLAUDE.md, every tax-rule cites legal authority + URL.
    DE25-22 cites § 36 Abs. 2 EStG, § 32d Abs. 1 EStG, and InvStG § 20.
    """

    def _facts(
        self,
        *,
        ordinary_refund_before_capital_eur: Decimal,
        capital_tax_with_teilfreistellung_before_treaty_eur: Decimal,
        capital_tax_with_teilfreistellung_after_treaty_eur: Decimal,
        domestic_capital_withholding_credit_eur: Decimal,
        children_applied_relief_eur: Decimal = Decimal("0.00"),
        children_guenstigerpruefung_choice: str = "kindergeld",
        children_kindergeld_total_eur: Decimal = Decimal("0.00"),
    ) -> dict[str, Decimal]:
        return germany_final_initial_facts_2025(
            ordinary_refund_before_capital_eur=ordinary_refund_before_capital_eur,
            capital_tax_with_teilfreistellung_before_treaty_eur=(
                capital_tax_with_teilfreistellung_before_treaty_eur
            ),
            capital_tax_with_teilfreistellung_after_treaty_eur=(
                capital_tax_with_teilfreistellung_after_treaty_eur
            ),
            domestic_capital_withholding_credit_eur=(
                domestic_capital_withholding_credit_eur
            ),
            children_applied_relief_eur=children_applied_relief_eur,
            children_guenstigerpruefung_choice=(
                children_guenstigerpruefung_choice
            ),
            children_kindergeld_total_eur=children_kindergeld_total_eur,
        )

    def test_stage_declared_in_germany_law_stages(self) -> None:
        # DE25-22 is the last legal-math stage in germany_law_stages_2025().
        # WS-4C added DE25-FORM-KAP-PROJECTION after it as a tail-of-tuple
        # form-line projection stage (form-binding only, no new legal math),
        # so we locate DE25-22 by id and verify it sits between the capital
        # graph's tail (DE25-21) and the form-projection stage rather than
        # asserting it's the global last entry.
        stages = germany_law_stages_2025()
        ids = [stage.stage_id for stage in stages]
        self.assertIn("DE25-22-FINAL-REFUND", ids)
        last_legal_math_index = ids.index("DE25-22-FINAL-REFUND")
        # DE25-21 (final capital tax) must precede DE25-22 (final refund).
        self.assertLess(ids.index("DE25-21-FINAL-CAPITAL-TAX"), last_legal_math_index)
        last = stages[last_legal_math_index]
        self.assertEqual(last.stage_id, "DE25-22-FINAL-REFUND")
        self.assertEqual(last.country_or_scope, "DE-2025")
        # Citations: § 36 Abs. 2 EStG (controlling authority), § 32d
        # Abs. 1 EStG (capital tax component), InvStG § 20 (Teilfreistellung).
        self.assertIn("§ 36 Abs. 2 EStG", last.legal_refs)
        self.assertIn("§ 32d Abs. 1 EStG", last.legal_refs)
        self.assertIn("InvStG § 20", last.legal_refs)
        # ESTG_36_URL must be in authority_urls so the audit trail
        # cites the controlling Hauptvordruck Erstattung authority.
        self.assertIn(
            "https://www.gesetze-im-internet.de/estg/__36.html",
            last.authority_urls,
        )
        # The headline output is classified RECONCILIATION_INVARIANT
        # to mirror DE25-21-FINAL-CAPITAL-TAX (the § 32d-final number
        # is read by the FormEntry JSON-key path, not by
        # ``_required_form_line``; per invariant I3, declaring a
        # FormLineRef that no _required_form_line consumes would be
        # an orphan declaration).
        target_decl = next(
            decl for decl in last.outputs if decl.key == "de.final.target_refund_eur"
        )
        self.assertIn(
            AuditWaypoint.RECONCILIATION_INVARIANT, target_decl.audit_waypoints
        )

    def test_calculate_matches_germany_model_formula(self) -> None:
        # Pin the formula germany_model.py:317-335 used to compute:
        # final_target = (ordinary_refund_before_capital - capital_tax_after_treaty)
        #                + domestic_capital_withholding_credit
        # refund_before_treaty = ordinary_refund_before_capital - capital_tax_before_treaty
        # Authority: § 36 Abs. 2 EStG (refund balance) / § 32d Abs. 1 EStG.
        facts = self._facts(
            ordinary_refund_before_capital_eur=D("5000.00"),
            capital_tax_with_teilfreistellung_before_treaty_eur=D("1500.00"),
            capital_tax_with_teilfreistellung_after_treaty_eur=D("1200.00"),
            domestic_capital_withholding_credit_eur=D("400.00"),
        )
        outputs = de25_22_final_refund(facts)
        self.assertEqual(outputs["de.final.refund_before_treaty_eur"], D("3500.00"))
        self.assertEqual(
            outputs["de.final.chosen_refund_before_domestic_certificate_eur"],
            D("3800.00"),
        )
        self.assertEqual(outputs["de.final.target_refund_eur"], D("4200.00"))

    def test_executor_records_outputs_in_rule_graph(self) -> None:
        # End-to-end: ``execute_germany_final_rule_graph`` produces a
        # ``RuleGraphExecution`` whose final facts include the headline
        # refund value (the I2 progress condition — the value lives
        # inside the rule graph rather than in script-level arithmetic).
        facts = self._facts(
            ordinary_refund_before_capital_eur=D("7321.45"),
            capital_tax_with_teilfreistellung_before_treaty_eur=D("987.65"),
            capital_tax_with_teilfreistellung_after_treaty_eur=D("765.43"),
            domestic_capital_withholding_credit_eur=D("123.45"),
        )
        execution = execute_germany_final_rule_graph(
            facts,
            input_fingerprints=germany_final_initial_fingerprints_2025(facts),
        )
        # final_target = (7321.45 - 765.43) + 123.45 = 6679.47
        self.assertEqual(
            execution.final_facts["de.final.target_refund_eur"],
            D("6679.47"),
        )
        # StageResult fingerprints exist for the headline output (audit
        # invariant: every value the renderer reads must trace to a
        # fingerprint chain in legal-execution-graph.json).
        self.assertEqual(len(execution.stage_results), 1)
        result = execution.stage_results[0]
        self.assertEqual(result.stage_id, "DE25-22-FINAL-REFUND")
        self.assertIn("de.final.target_refund_eur", result.output_fingerprints)
        self.assertIn(
            "de.final.refund_before_treaty_eur", result.output_fingerprints
        )
        self.assertIn(
            "de.final.chosen_refund_before_domestic_certificate_eur",
            result.output_fingerprints,
        )

if __name__ == "__main__":
    unittest.main()
