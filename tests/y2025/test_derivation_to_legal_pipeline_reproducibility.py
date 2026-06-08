"""Reproducibility contract for the two-pipeline architecture (WS-5H).

Per ``docs/invariant-migration-plan.md`` §1.5: re-running Pipeline 2
(the existing DE25-* / US25-* / TREATY25- legal stages) from a
persisted ``derived-facts.json`` must produce a byte-identical
``final-legal-output.json``. This isolates Pipeline 1 bugs (raw-data
drift) from Pipeline 2 bugs (legal-interpretation drift).

WS-5H stop condition: Pipeline 1 currently has zero registered
stages, so ``derived-facts.json`` lands empty. The reproducibility
contract still applies — the framework infrastructure (atomic writes,
deterministic execution, persisted boundary state) is what's under
test. WS-5A and WS-5B will register concrete derivation stages that
make the contract substantive; until then this test validates the
scaffold so any future Pipeline-1-stage churn that breaks Pipeline 2
reproducibility is caught immediately.

Authority: § 32d Abs. 5 EStG per-Posten audit-trail rigor
(https://www.gesetze-im-internet.de/estg/__32d.html) and InvStG § 2
Abs. 6 fund taxonomy
(https://www.gesetze-im-internet.de/invstg_2018/__2.html) require
that derived-fact regeneration is deterministic.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.derivation import (
    DERIVATION_FACTS_NAME,
    DERIVATION_GRAPH_NAME,
    derivation_facts_path,
    derivation_graph_path,
)
from tax_pipeline.pipelines.y2025.final_legal_output import (
    FINAL_LEGAL_OUTPUT_NAME,
    final_legal_output_path,
)
from tax_pipeline.run_year import run_year


def _capture_run_year(project_root: Path, paths) -> None:
    """Run ``run_year`` against the materialized demo workspace, swallowing stdout."""
    with redirect_stdout(io.StringIO()):
        run_year(project_root, "2025", workspace_root=paths.year_root)


class DerivationToLegalPipelineReproducibilityTest(unittest.TestCase):
    def test_pipeline2_byte_identical_when_pipeline1_skipped_on_rerun(self) -> None:
        # Step 1: materialize the demo workspace and run BOTH pipelines
        # end-to-end. Captures the canonical ``final-legal-output.json``
        # bytes plus the persisted Pipeline 1 artifacts on disk.
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            paths = materialize_demo_workspace(project_root, demo_name="demo-2025", year=2025)
            _capture_run_year(project_root, paths)

            final_path = final_legal_output_path(paths)
            facts_path = derivation_facts_path(paths)
            graph_path = derivation_graph_path(paths)

            self.assertTrue(final_path.exists(), "Pipeline 2 must produce final-legal-output.json")
            self.assertTrue(facts_path.exists(), "Pipeline 1 must produce derived-facts.json")
            self.assertTrue(graph_path.exists(), "Pipeline 1 must produce derivation-graph.json")
            self.assertEqual(final_path.name, FINAL_LEGAL_OUTPUT_NAME)
            self.assertEqual(facts_path.name, DERIVATION_FACTS_NAME)
            self.assertEqual(graph_path.name, DERIVATION_GRAPH_NAME)

            first_final_bytes = final_path.read_bytes()
            first_facts_bytes = facts_path.read_bytes()
            first_graph_bytes = graph_path.read_bytes()

            # Step 2: re-run with Pipeline 1 (run_derivation) skipped.
            # The persisted ``derived-facts.json`` / ``derivation-graph.json``
            # from step 1 stay on disk untouched; Pipeline 2 reads workspace
            # inputs unchanged. The byte-equality contract under test is:
            # given identical Pipeline 1 outputs (which includes "no
            # outputs" while WS-5A / WS-5B haven't landed), Pipeline 2 is
            # deterministic.
            #
            # We mock ``_run_pipeline_module`` only for the run_derivation
            # module — every other module runs normally.
            from tax_pipeline import run_year as run_year_module

            real_run = run_year_module._run_pipeline_module
            skipped: list[str] = []

            def selective_runner(module_name: str, *, env, cwd):
                if module_name == "tax_pipeline.pipelines.y2025.run_derivation":
                    skipped.append(module_name)
                    return None
                return real_run(module_name, env=env, cwd=cwd)

            with mock.patch.object(
                run_year_module,
                "_run_pipeline_module",
                side_effect=selective_runner,
            ):
                _capture_run_year(project_root, paths)

            # Sanity: the mock observed the skip. If the pipeline-module
            # ordering ever drifted such that run_derivation was no longer
            # invoked, this assertion would surface it.
            self.assertEqual(
                skipped,
                ["tax_pipeline.pipelines.y2025.run_derivation"],
                "selective runner expected to skip Pipeline 1 exactly once",
            )

            second_final_bytes = final_path.read_bytes()
            second_facts_bytes = facts_path.read_bytes()
            second_graph_bytes = graph_path.read_bytes()

            # The §1.5 boundary contract: given the same persisted
            # derived-facts, Pipeline 2 produces the same final-legal-output
            # bytes. The empty-Pipeline-1 case is the WS-5H landing.
            self.assertEqual(
                second_final_bytes,
                first_final_bytes,
                "Pipeline 2 must be byte-identical when re-run from "
                "persisted derived-facts.json",
            )

            # Pipeline 1 artifacts were not regenerated (Pipeline 1 was
            # skipped on the second pass) — verify they're untouched
            # rather than coincidentally identical. This guards against a
            # future bug where Pipeline 2 silently rewrites the boundary
            # state.
            self.assertEqual(second_facts_bytes, first_facts_bytes)
            self.assertEqual(second_graph_bytes, first_graph_bytes)


if __name__ == "__main__":
    unittest.main()
