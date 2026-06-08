"""Invariant I7: every ``LawRule.calculate`` body reads only the keys
declared in its ``LawStage.input_fact_keys``.

Per project CLAUDE.md, the audit principle is that "the final output tells
the user which form lines each value flows through, which should be
auditable on a function by function basis as well as an end to end
decision tree basis." That auditability requires every input to a rule
to be a declared edge in the rule graph; an undeclared read means the
audit graph is missing a real data dependency.

Per § 32d Abs. 5 EStG (https://www.gesetze-im-internet.de/estg/__32d.html)
the residence-state foreign-tax-credit must trace each Posten-level fact
to its source. The same data-flow rigor applies to every rule input —
silently reaching past ``input_fact_keys`` defeats the audit-trail
guarantee.

This test exercises the runtime tracking guard installed in
``execute_rule_graph``: facts are wrapped in a ``TrackingMapping`` that
records every key read; after each ``calculate`` returns, the executor
asserts the read set is a subset of the declared inputs and otherwise
raises ``RuleInputDeclarationError``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from typing import Any, Mapping

from tax_pipeline.core.stages import (
    AuditWaypoint,
    LawRule,
    LawStage,
    OutputDeclaration,
    RuleInputDeclarationError,
    execute_rule_graph,
)


def _stage(*, stage_id: str, input_keys: tuple[str, ...], output_key: str) -> LawStage:
    return LawStage(
        stage_id=stage_id,
        country_or_scope="TEST-2025",
        legal_refs=("Test Authority",),
        authority_urls=("https://example.test/authority",),
        input_fact_keys=input_keys,
        rounding_policy="no rounding",
        law_order_note="Test stage for input-tracking invariant.",
        legal_formula=f"{output_key} := test computation per Test Authority",
        narrative_templates={"de": stage_id, "en": stage_id},
        outputs=(
            OutputDeclaration(
                key=output_key,
                audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
            ),
        ),
    )


class RuleInputTrackingTest(unittest.TestCase):
    """The tracking dict surfaces undeclared-key reads at runtime."""

    def test_undeclared_input_read_raises(self) -> None:
        """A rule that reads ``test.b`` while only declaring ``test.a`` must
        be rejected by the executor with ``RuleInputDeclarationError``
        listing ``test.b`` as the offender."""

        stage = _stage(
            stage_id="DE25-TEST-UNDECLARED",
            input_keys=("test.a",),
            output_key="test.out",
        )

        def calculate(facts: Mapping[str, Any]) -> Mapping[str, Any]:
            # Reads "test.b" which is NOT in input_fact_keys — this must
            # be caught at runtime so the audit graph never silently loses
            # a data-dependency edge.
            _ = facts["test.b"]
            return {"test.out": Decimal("1")}

        rule = LawRule(
            stage=stage,
            implementation_ref="tests.test_rule_input_tracking",
            calculate=calculate,
        )

        with self.assertRaises(RuleInputDeclarationError) as ctx:
            execute_rule_graph(
                initial_facts={
                    "test.a": Decimal("1"),
                    "test.b": Decimal("2"),
                },
                rules=(rule,),
            )

        self.assertIn("DE25-TEST-UNDECLARED", str(ctx.exception))
        self.assertIn("test.b", str(ctx.exception))
        self.assertEqual(ctx.exception.stage_id, "DE25-TEST-UNDECLARED")
        self.assertEqual(ctx.exception.undeclared_keys, frozenset({"test.b"}))

    def test_declared_inputs_only_runs_cleanly(self) -> None:
        """A rule that reads only declared keys executes without error."""

        stage = _stage(
            stage_id="DE25-TEST-DECLARED",
            input_keys=("test.a", "test.b"),
            output_key="test.out",
        )

        def calculate(facts: Mapping[str, Any]) -> Mapping[str, Any]:
            return {"test.out": facts["test.a"] + facts["test.b"]}

        rule = LawRule(
            stage=stage,
            implementation_ref="tests.test_rule_input_tracking",
            calculate=calculate,
        )

        execution = execute_rule_graph(
            initial_facts={
                "test.a": Decimal("1"),
                "test.b": Decimal("2"),
            },
            rules=(rule,),
        )

        self.assertEqual(execution.final_facts["test.out"], Decimal("3"))

    def test_contains_check_counts_as_read(self) -> None:
        """``key in facts`` is a read — using it to bypass declared inputs
        must also be caught (otherwise authors could probe unnamed keys)."""

        stage = _stage(
            stage_id="DE25-TEST-CONTAINS-PROBE",
            input_keys=("test.a",),
            output_key="test.out",
        )

        def calculate(facts: Mapping[str, Any]) -> Mapping[str, Any]:
            _probe = "test.b" in facts  # noqa: F841 — explicit probe
            return {"test.out": Decimal("0")}

        rule = LawRule(
            stage=stage,
            implementation_ref="tests.test_rule_input_tracking",
            calculate=calculate,
        )

        with self.assertRaises(RuleInputDeclarationError) as ctx:
            execute_rule_graph(
                initial_facts={"test.a": Decimal("1"), "test.b": Decimal("2")},
                rules=(rule,),
            )

        self.assertIn("test.b", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
