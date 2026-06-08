"""TDD test for ``BRIDGE25-FOREIGN-TAX-RECONCILIATION`` (WS-4A).

The bridge stage replaces the script-level reconciliation block at
``germany_model.py:259-269`` (flagged by I2 / I5 in
``docs/invariant-migration-plan.md``). Promoting the assertion into a
``LawRule.calculate`` body brings the verified total inside the audit
graph: ``StageResult`` fingerprints commit to both the four input
components and the reconciliation total, and a discrepancy raises a
typed ``LegalInvariantViolation`` rather than a script-level
``ValueError``.

Authority:
- § 32d Abs. 5 EStG (per-Posten foreign-tax credit) — the foreign-tax
  basis must reconcile to the per-item totals consumed by the § 32d(5)
  cap. https://www.gesetze-im-internet.de/estg/__32d.html
- 26 U.S.C. § 901 (foreign tax credit) — verifiable foreign-tax-paid
  basis on Form 1116.
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
- DBA-USA Art. 23 — residence-state credit ties the U.S. and German
  foreign-tax-credit chains across jurisdictions.
  https://www.irs.gov/pub/irs-trty/germany.pdf
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.bridge_rules import (
    bridge25_foreign_tax_reconciliation,
    bridge_initial_facts_2025,
    bridge_initial_fingerprints_2025,
    execute_bridge_rule_graph,
)
from tax_pipeline.y2025.bridge_stages import (
    BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
    bridge_law_stages_2025,
)
from tax_pipeline.core.stages import AuditWaypoint, LegalInvariantViolation


D = Decimal


class BridgeForeignTaxReconciliationTest(unittest.TestCase):
    """Per CLAUDE.md, every tax-rule cites legal authority + URL.
    The reconciliation invariant cites § 32d Abs. 5 EStG, 26 U.S.C. § 901,
    and DBA-USA Art. 23. The stage outputs a verified total and a
    ``"reconciled"`` status, both classified
    ``AuditWaypoint.RECONCILIATION_INVARIANT``.
    """

    def _facts(
        self,
        *,
        foreign_tax_1099_eur: Decimal,
        bank_credited_eur: Decimal,
        bank_not_credited_eur: Decimal,
        treaty_us_source_eur: Decimal,
        capital_total_eur: Decimal,
    ) -> dict[str, Decimal]:
        return bridge_initial_facts_2025(
            foreign_tax_1099_eur=foreign_tax_1099_eur,
            bank_certificate_foreign_tax_credited_eur=bank_credited_eur,
            bank_certificate_foreign_tax_not_credited_eur=bank_not_credited_eur,
            treaty_us_source_dividend_allowed_us_tax_eur=treaty_us_source_eur,
            capital_explicit_foreign_tax_total_eur=capital_total_eur,
        )

    def test_stage_declared_with_reconciliation_invariant_waypoint(self) -> None:
        stages = bridge_law_stages_2025()
        self.assertEqual(len(stages), 1)
        stage = stages[0]
        self.assertEqual(
            stage.stage_id, BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID
        )
        self.assertEqual(stage.country_or_scope, "BRIDGE-2025")
        # Both outputs must carry RECONCILIATION_INVARIANT per
        # invariant-migration-plan.md §6 WS-4A.
        for decl in stage.outputs:
            self.assertIn(
                AuditWaypoint.RECONCILIATION_INVARIANT, decl.audit_waypoints
            )
        # Citations: § 32d Abs. 5 EStG, 26 U.S.C. § 901, DBA-USA Art. 23.
        self.assertIn("§ 32d Abs. 5 EStG", stage.legal_refs)
        self.assertIn("26 U.S.C. § 901", stage.legal_refs)
        self.assertIn("DBA-USA Art. 23", stage.legal_refs)

    def test_reconciled_facts_produce_verified_total_and_status(self) -> None:
        facts = self._facts(
            foreign_tax_1099_eur=D("100.00"),
            bank_credited_eur=D("50.00"),
            bank_not_credited_eur=D("25.00"),
            treaty_us_source_eur=D("15.00"),
            capital_total_eur=D("190.00"),
        )
        outputs = bridge25_foreign_tax_reconciliation(facts)
        self.assertEqual(
            outputs["bridge.foreign_tax_reconciliation_total_eur"],
            D("190.00"),
        )
        self.assertEqual(
            outputs["bridge.foreign_tax_reconciliation_status"], "reconciled"
        )

    def test_reconciliation_failure_raises_legal_invariant_violation(self) -> None:
        # Components sum to 190.00 but capital total is 200.00 — must
        # fail closed per § 32d Abs. 5 EStG / 26 U.S.C. § 901.
        facts = self._facts(
            foreign_tax_1099_eur=D("100.00"),
            bank_credited_eur=D("50.00"),
            bank_not_credited_eur=D("25.00"),
            treaty_us_source_eur=D("15.00"),
            capital_total_eur=D("200.00"),
        )
        with self.assertRaises(LegalInvariantViolation) as ctx:
            bridge25_foreign_tax_reconciliation(facts)
        self.assertEqual(
            ctx.exception.stage_id,
            BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
        )
        # Surface the offending components so an auditor can pinpoint
        # which input drifted.
        self.assertIn("190.00", str(ctx.exception))
        self.assertIn("200.00", str(ctx.exception))

    def test_executor_surfaces_violation_with_stage_id(self) -> None:
        # End-to-end: ``execute_bridge_rule_graph`` runs the rule via
        # the standard executor; a violation propagates with the
        # ``stage_id`` so the pipeline aborts at the seam.
        facts = self._facts(
            foreign_tax_1099_eur=D("10.00"),
            bank_credited_eur=D("0.00"),
            bank_not_credited_eur=D("0.00"),
            treaty_us_source_eur=D("0.00"),
            capital_total_eur=D("99.99"),
        )
        with self.assertRaises(LegalInvariantViolation) as ctx:
            execute_bridge_rule_graph(
                facts,
                input_fingerprints=bridge_initial_fingerprints_2025(facts),
            )
        self.assertEqual(
            ctx.exception.stage_id,
            BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
        )

    def test_executor_records_outputs_in_rule_graph(self) -> None:
        # End-to-end: ``execute_bridge_rule_graph`` produces a
        # ``RuleGraphExecution`` whose final facts include the verified
        # total (the I2 progress condition — the value lives inside the
        # rule graph rather than in script-level arithmetic).
        facts = self._facts(
            foreign_tax_1099_eur=D("12.34"),
            bank_credited_eur=D("56.78"),
            bank_not_credited_eur=D("9.01"),
            treaty_us_source_eur=D("2.34"),
            capital_total_eur=D("80.47"),
        )
        execution = execute_bridge_rule_graph(
            facts,
            input_fingerprints=bridge_initial_fingerprints_2025(facts),
        )
        self.assertEqual(
            execution.final_facts[
                "bridge.foreign_tax_reconciliation_total_eur"
            ],
            D("80.47"),
        )
        self.assertEqual(
            execution.final_facts["bridge.foreign_tax_reconciliation_status"],
            "reconciled",
        )
        # StageResult fingerprints exist for both outputs (audit
        # invariant: every value the renderer reads must trace to a
        # fingerprint chain in legal-execution-graph.json).
        self.assertEqual(len(execution.stage_results), 1)
        result = execution.stage_results[0]
        self.assertIn(
            "bridge.foreign_tax_reconciliation_total_eur",
            result.output_fingerprints,
        )
        self.assertIn(
            "bridge.foreign_tax_reconciliation_status",
            result.output_fingerprints,
        )


if __name__ == "__main__":
    unittest.main()
