"""Framework-level test for Pipeline 1 (Derivation).

Per ``docs/invariant-migration-plan.md`` §1.5 the Derivation pipeline
consumes raw inputs and emits canonical derived facts persisted to
``derived-facts.json`` + ``derivation-graph.json``. WS-5H lands the
empty framework — no Pipeline 1 stages are registered yet — so this
test constructs a minimal Pipeline 1 inline (one trivial stage) to
exercise the runtime + persistence + round-trip contract before
WS-5A / WS-5B register real stages.

Authority context: derived facts feed § 32d Abs. 5 EStG per-Posten
foreign-tax credit calculations
(https://www.gesetze-im-internet.de/estg/__32d.html) and InvStG § 2
Abs. 6 fund-type taxonomy
(https://www.gesetze-im-internet.de/invstg_2018/__2.html). A
deterministic, fingerprinted derivation pipeline is required so the
audit trail covers BOTH "did we read the raw inputs correctly?" and
"did we apply the law correctly?" — see §1.5 of the plan for the
boundary contract.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.core.stages import (
    AuditWaypoint,
    LawRule,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.derivation import (
    DERIVATION_FACTS_NAME,
    DERIVATION_GRAPH_NAME,
    derivation_facts_path,
    derivation_graph_path,
    execute_derivation_pipeline,
    germany_derivation_law_rules_2025,
    usa_derivation_law_rules_2025,
    write_derivation_artifacts,
)
from tax_pipeline.derivation.persistence import load_derivation_facts
from tax_pipeline.paths import YearPaths


def _trivial_stage() -> LawStage:
    """A single Pipeline 1 stage that doubles a dummy input.

    Mimics the WS-5A / WS-5B shape: ``DERIVE-`` stage_id prefix,
    no form_line_refs (Pipeline 1 outputs are derived facts, not
    form-bound legal values), ``PER_POSTEN_AGGREGATION`` waypoint as
    the §1.5 plan suggests for derivation aggregations.
    """
    return LawStage(
        stage_id="DERIVE-DE25-TEST-FRAMEWORK-DOUBLE",
        country_or_scope="TEST-2025",
        legal_refs=("test framework: derived-fact aggregation",),
        # The plan's §1.5 shape: derivations cite the source-law authority
        # for the aggregation convention. Test stage cites § 32d Abs. 5
        # EStG (per-Posten audit-trail rigor) for the WS-5H placeholder.
        authority_urls=("https://www.gesetze-im-internet.de/estg/__32d.html",),
        input_fact_keys=("test.derive.raw_value",),
        rounding_policy=(
            "Test fixture: identity-pass-through Decimal arithmetic; "
            "no monetary rounding applies in Pipeline 1 framework tests."
        ),
        law_order_note=(
            "Test fixture: derivation runs before any legal "
            "interpretation per §1.5 boundary contract."
        ),
        legal_formula="test.derive.doubled = test.derive.raw_value * 2",
        narrative_templates={"en": "DERIVE-DE25-TEST-FRAMEWORK-DOUBLE"},
        outputs=(
            OutputDeclaration(
                key="test.derive.doubled",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


def _trivial_rule() -> LawRule:
    return LawRule(
        stage=_trivial_stage(),
        implementation_ref="tests.test_derivation_pipeline_framework:_trivial_rule",
        calculate=lambda facts: {
            "test.derive.doubled": facts["test.derive.raw_value"] * Decimal("2"),
        },
    )


class DerivationPipelineFrameworkTest(unittest.TestCase):
    def test_framework_executes_persists_and_round_trips(self) -> None:
        # WS-5B + WS-5A populate the German Pipeline 1 factory with 6
        # stages: DERIVE-DE25-FUND-CLASSIFICATION (5B) plus the five
        # DE25-13 derivation extractions (5A). Every stage uses the
        # DERIVE-DE25- prefix so framework callers can filter by
        # pipeline/jurisdiction without parsing stage bodies.
        for rule in germany_derivation_law_rules_2025():
            self.assertTrue(
                rule.stage.stage_id.startswith("DERIVE-DE25-"),
                rule.stage.stage_id,
            )
        # USA Pipeline 1 stays empty until a separate workstream lands.
        self.assertEqual(usa_derivation_law_rules_2025(), ())

        # Empty Pipeline 1 short-circuits to a pass-through:
        # ``final_facts`` equals the supplied initial facts and the
        # graph_dict has zero nodes / zero edges. This is the state
        # Pipeline 2 sees on the WS-5H landing commit.
        empty_result = execute_derivation_pipeline({}, ())
        self.assertIsNone(empty_result.execution)
        self.assertEqual(empty_result.final_facts, {})
        self.assertEqual(empty_result.graph_dict["stage_ids"], [])
        self.assertEqual(empty_result.graph_dict["nodes"], [])
        self.assertEqual(empty_result.graph_dict["edges"], [])

        # Minimal Pipeline 1 with ONE trivial stage. The runtime
        # delegates to ``execute_rule_graph``, so tracking-dict (I7),
        # canonical-fingerprint (I6), and declared-output (I8)
        # invariants apply here exactly as for Pipeline 2.
        result = execute_derivation_pipeline(
            {"test.derive.raw_value": Decimal("21")},
            (_trivial_rule(),),
        )
        self.assertIsNotNone(result.execution)
        self.assertEqual(result.final_facts["test.derive.doubled"], Decimal("42"))
        self.assertEqual(
            [node["rule_id"] for node in result.graph_dict["nodes"]],
            ["DERIVE-DE25-TEST-FRAMEWORK-DOUBLE"],
        )
        self.assertEqual(result.graph_dict["edges"], [])
        self.assertIn(
            "test.derive.raw_value",
            result.graph_dict["initial_fact_keys"],
        )

        # Persist artifacts to a workspace's derivation_root and assert
        # atomic-write contract (no orphan ``.tmp`` siblings) plus
        # JSON round-trip equality. The atomic-write helper is shared
        # with ``write_final_legal_output_2025`` so this also covers
        # the framework's reuse of the WS-2E / H9 fix.
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            workspace_root = project_root / "workspace"
            paths = YearPaths.for_workspace(project_root, workspace_root, 2025)
            paths.ensure_directories()

            facts_path, graph_path = write_derivation_artifacts(paths, result)

            # Files land under ``paths.derivation_root`` with the
            # canonical names so audit tooling can locate them without
            # hunting through ``analysis-steps``.
            self.assertEqual(facts_path, derivation_facts_path(paths))
            self.assertEqual(graph_path, derivation_graph_path(paths))
            self.assertTrue(facts_path.exists())
            self.assertTrue(graph_path.exists())
            self.assertEqual(facts_path.name, DERIVATION_FACTS_NAME)
            self.assertEqual(graph_path.name, DERIVATION_GRAPH_NAME)
            self.assertEqual(facts_path.parent, paths.derivation_root)
            self.assertEqual(graph_path.parent, paths.derivation_root)

            # Atomic-write post-condition: no orphan tempfile siblings.
            leftovers = sorted(p.name for p in paths.derivation_root.glob("*.tmp"))
            self.assertEqual(leftovers, [], f"orphan temp files: {leftovers}")

            # JSON round-trip: written contents parse cleanly and match
            # the in-memory shape after the encoder's canonicalization
            # (Decimal -> fixed-point string).
            facts_payload = json.loads(facts_path.read_text(encoding="utf-8"))
            graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(facts_payload["schema_version"], 1)
            self.assertIn("test.derive.doubled", facts_payload["facts"])
            self.assertEqual(facts_payload["facts"]["test.derive.doubled"], "42")
            self.assertEqual(facts_payload["facts"]["test.derive.raw_value"], "21")
            self.assertEqual(
                graph_payload["stage_ids"],
                ["DERIVE-DE25-TEST-FRAMEWORK-DOUBLE"],
            )
            self.assertEqual(graph_payload["edges"], [])

            # The loader extracts the inner facts dict so Pipeline 2 (and
            # the reproducibility test) get the right surface back.
            loaded_facts = load_derivation_facts(paths)
            self.assertEqual(loaded_facts["test.derive.doubled"], "42")
            self.assertEqual(loaded_facts["test.derive.raw_value"], "21")

            # Re-running write_derivation_artifacts is idempotent: the
            # second pass yields byte-identical files (deterministic
            # serialization) and still leaves no tempfile leftovers.
            first_bytes = facts_path.read_bytes()
            write_derivation_artifacts(paths, result)
            self.assertEqual(facts_path.read_bytes(), first_bytes)
            leftovers_after = sorted(
                p.name for p in paths.derivation_root.glob("*.tmp")
            )
            self.assertEqual(leftovers_after, [])


if __name__ == "__main__":
    unittest.main()
