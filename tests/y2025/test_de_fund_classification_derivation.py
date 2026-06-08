"""WS-5B test: ``DERIVE-DE25-FUND-CLASSIFICATION`` Pipeline 1 stage.

Pins the InvStG § 2 Abs. 6 fund-classification merge per
``docs/invariant-migration-plan.md`` §1.5 / §7 WS-5B.

Authority:
- InvStG § 2 Abs. 6: https://www.gesetze-im-internet.de/invstg_2018/__2.html
- InvStG § 20: https://www.gesetze-im-internet.de/invstg_2018/__20.html
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.derivation import (
    execute_derivation_pipeline,
    germany_derivation_law_rules_2025,
    write_derivation_artifacts,
)
from tax_pipeline.y2025.derivation.germany_derivations import (
    DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID,
    FUND_CLASSIFICATION_INPUT_AKTIENFONDS,
    FUND_CLASSIFICATION_INPUT_FUND_TYPES,
    FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS,
    FUND_CLASSIFICATION_INPUT_REPO_CSV,
    FUND_CLASSIFICATION_OUTPUT_KEY,
)
from tax_pipeline.derivation.persistence import (
    derivation_facts_path,
    derivation_graph_path,
)
from tax_pipeline.fund_classification_data import merge_fund_classification
from tax_pipeline.paths import YearPaths


# Small, deterministic fixture exercising every override branch. Repo CSV
# starts with two known classifications; the override map overwrites VOO,
# the bulk lists add a brand-new symbol on each side, and the bulk
# aktienfonds list also re-promotes a symbol the override map placed on
# the sonstige side to verify the documented application order
# (repo → fund_types → non_aktienfonds → aktienfonds).
_FIXTURE_REPO_CSV = {"VOO": "aktienfonds", "GLD": "sonstige"}
_FIXTURE_FUND_TYPES = {
    "VOO": "sonstige",  # explicit override flips repo classification
    "PROMOTE": "sonstige",  # later bulk aktienfonds list re-promotes this
    "  vti  ": "aktienfonds",  # symbol normalization (whitespace + casing)
}
_FIXTURE_NON_AKTIENFONDS = ["IBIT", "OTHER_BOND"]
_FIXTURE_AKTIENFONDS = ["NEW_EQUITY", "PROMOTE"]


class FundClassificationMergeTest(unittest.TestCase):
    """Pure-function merge: deterministic, no I/O."""

    def test_merge_pins_workspace_override_application_order(self) -> None:
        merged = merge_fund_classification(
            _FIXTURE_REPO_CSV,
            _FIXTURE_FUND_TYPES,
            _FIXTURE_NON_AKTIENFONDS,
            _FIXTURE_AKTIENFONDS,
        )
        # Repo baseline preserved when no override touches the symbol.
        self.assertEqual(merged["GLD"], "sonstige")
        # Override map overrides the repo value.
        self.assertEqual(merged["VOO"], "sonstige")
        # Symbol normalization: strip + upper.
        self.assertEqual(merged["VTI"], "aktienfonds")
        # non_aktienfonds list adds new entries as 'sonstige'.
        self.assertEqual(merged["IBIT"], "sonstige")
        self.assertEqual(merged["OTHER_BOND"], "sonstige")
        # aktienfonds list adds new entries as 'aktienfonds'.
        self.assertEqual(merged["NEW_EQUITY"], "aktienfonds")
        # Application order: aktienfonds list runs LAST, so PROMOTE
        # ends up 'aktienfonds' even though the explicit map said
        # 'sonstige'. Pinning this preserves the legacy loader semantics.
        self.assertEqual(merged["PROMOTE"], "aktienfonds")

    def test_merge_fails_closed_on_invalid_inputs(self) -> None:
        # CLAUDE.md fail-closed discipline: unknown taxonomy label and
        # non-mapping fund_types both raise instead of silently aliasing.
        with self.assertRaises(ValueError):
            merge_fund_classification({}, {"BOGUS": "thematic_fund"}, [], [])
        with self.assertRaises(ValueError):
            merge_fund_classification({}, ["VOO"], [], [])  # type: ignore[arg-type]


class FundClassificationDerivationStageTest(unittest.TestCase):
    """Stage executes via Pipeline 1 and lands in the persisted artifacts."""

    def test_stage_executes_and_outputs_match_pure_merge(self) -> None:
        all_rules = germany_derivation_law_rules_2025()
        # WS-5B's fund-classification stage is one of several Pipeline 1
        # stages registered in the factory; isolate it for this test.
        rules = tuple(
            r
            for r in all_rules
            if r.stage.stage_id == DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID
        )
        self.assertEqual(len(rules), 1)

        initial_facts = {
            FUND_CLASSIFICATION_INPUT_REPO_CSV: _FIXTURE_REPO_CSV,
            FUND_CLASSIFICATION_INPUT_FUND_TYPES: _FIXTURE_FUND_TYPES,
            FUND_CLASSIFICATION_INPUT_AKTIENFONDS: _FIXTURE_AKTIENFONDS,
            FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS: _FIXTURE_NON_AKTIENFONDS,
        }
        result = execute_derivation_pipeline(initial_facts, rules)

        self.assertIsNotNone(result.execution)
        merged = result.final_facts[FUND_CLASSIFICATION_OUTPUT_KEY]
        # Stage output is byte-for-byte identical to the pure merge.
        expected = merge_fund_classification(
            _FIXTURE_REPO_CSV,
            _FIXTURE_FUND_TYPES,
            _FIXTURE_NON_AKTIENFONDS,
            _FIXTURE_AKTIENFONDS,
        )
        self.assertEqual(merged, expected)

        # Audit-graph node carries the InvStG § 2 Abs. 6 citation.
        node = result.graph_dict["nodes"][0]
        self.assertEqual(node["rule_id"], DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID)
        self.assertIn("InvStG § 2 Abs. 6", node["legal_refs"])
        self.assertIn(
            "https://www.gesetze-im-internet.de/invstg_2018/__2.html",
            node["authority_urls"],
        )

    def test_stage_appears_in_persisted_derivation_graph(self) -> None:
        all_rules = germany_derivation_law_rules_2025()
        rules = tuple(
            r
            for r in all_rules
            if r.stage.stage_id == DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID
        )
        initial_facts = {
            FUND_CLASSIFICATION_INPUT_REPO_CSV: _FIXTURE_REPO_CSV,
            FUND_CLASSIFICATION_INPUT_FUND_TYPES: _FIXTURE_FUND_TYPES,
            FUND_CLASSIFICATION_INPUT_AKTIENFONDS: _FIXTURE_AKTIENFONDS,
            FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS: _FIXTURE_NON_AKTIENFONDS,
        }
        result = execute_derivation_pipeline(initial_facts, rules)

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            workspace_root = project_root / "workspace"
            paths = YearPaths.for_workspace(project_root, workspace_root, 2025)
            paths.ensure_directories()
            facts_path, graph_path = write_derivation_artifacts(paths, result)

            self.assertEqual(facts_path, derivation_facts_path(paths))
            self.assertEqual(graph_path, derivation_graph_path(paths))

            graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertIn(
                DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID,
                graph_payload["stage_ids"],
            )
            facts_payload = json.loads(facts_path.read_text(encoding="utf-8"))
            # ``de.derived.fund_classification`` is the typed Pipeline 2
            # boundary fact: serialized as a plain JSON object so any
            # Pipeline 2 consumer reads it without re-parsing.
            self.assertIn(
                FUND_CLASSIFICATION_OUTPUT_KEY,
                facts_payload["facts"],
            )
            persisted = facts_payload["facts"][FUND_CLASSIFICATION_OUTPUT_KEY]
            self.assertEqual(persisted["VOO"], "sonstige")
            self.assertEqual(persisted["NEW_EQUITY"], "aktienfonds")


if __name__ == "__main__":
    unittest.main()
