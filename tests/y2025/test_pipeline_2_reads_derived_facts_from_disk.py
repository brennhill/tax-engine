"""Pipeline 2 must read ``derived-facts.json`` from disk, not re-derive in memory.

This regression test makes the Pipeline 1 → Pipeline 2 boundary structurally
load-bearing per ``docs/invariant-migration-plan.md`` §1.5. Before this
change, ``germany_capital_initial_facts_2025`` re-ran the in-memory
derivation pipeline rather than reading the persisted artifact, so a
Pipeline 1 bug surfaced only as a Pipeline 2 failure (and a
``derived-facts.json`` mutation between runs was silently ignored).

The contract under test: if the operator mutates a single
``de.derived.source_country_classification.fund_types`` entry inside
``derived-facts.json``, re-running the Germany Pipeline 2 module
(``germany_model``) reads that mutation and propagates it to
``final-legal-output.json``. Concretely we flip a fund symbol from
``aktienfonds`` to ``sonstige``, which changes the InvStG § 20
partial-exemption rate (Teilfreistellung) the symbol's gains are taxed
at — equity Aktienfonds: 30 % exemption; sonstige Investmentfonds: 0 %
exemption. The change therefore moves the German capital-tax line by a
numerically observable amount.

Authority:
- InvStG § 20 (Teilfreistellung):
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
- InvStG § 2 Abs. 6 (fund taxonomy):
  https://www.gesetze-im-internet.de/invstg_2018/__2.html
- § 32d Abs. 5 EStG (per-Posten audit-trail rigor for derived facts):
  https://www.gesetze-im-internet.de/estg/__32d.html
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.derivation.persistence import derivation_facts_path
from tax_pipeline.pipelines.y2025.final_legal_output import final_legal_output_path
from tax_pipeline.run_year import run_year


def _capture_run_year(project_root: Path, paths) -> None:
    """Run ``run_year`` against the materialized demo workspace, swallowing stdout."""
    with redirect_stdout(io.StringIO()):
        run_year(project_root, "2025", workspace_root=paths.year_root)


def _read_facts(facts_path: Path) -> dict:
    return json.loads(facts_path.read_text(encoding="utf-8"))


def _write_facts(facts_path: Path, payload: dict) -> None:
    facts_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _german_capital_total_with_teilfreistellung(final_payload: dict) -> str:
    """Read the headline German capital-tax-with-Teilfreistellung total.

    This is the line item that responds to fund-classification changes:
    Aktienfonds carry a 30 % InvStG § 20 partial exemption; sonstige
    Investmentfonds carry 0 %, so flipping the type for a symbol that
    has positive fund gain shifts this number.
    """
    capital = final_payload["germany"]["forms"]["results"]["capital"]
    return capital["capital_tax_with_teilfreistellung_before_treaty_eur"]


class Pipeline2ReadsDerivedFactsFromDiskTest(unittest.TestCase):
    def test_mutation_in_derived_facts_propagates_to_final_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            paths = materialize_demo_workspace(project_root, demo_name="demo-2025", year=2025)

            # Step 1: full end-to-end run produces canonical artifacts.
            _capture_run_year(project_root, paths)
            facts_path = derivation_facts_path(paths)
            final_path = final_legal_output_path(paths)
            self.assertTrue(facts_path.exists())
            self.assertTrue(final_path.exists())

            baseline_final = json.loads(final_path.read_text(encoding="utf-8"))
            baseline_total = _german_capital_total_with_teilfreistellung(baseline_final)

            # Step 2: pick a fund symbol that's classified ``aktienfonds``
            # in ``de.derived.source_country_classification.fund_types`` AND
            # appears in the per-symbol fund gain map. DE25-14 looks up the
            # Teilfreistellung rate via that fund_types index, so this is
            # the field whose mutation must propagate end-to-end. Flipping
            # ``de.derived.fund_classification`` alone would not feed
            # DE25-14 because DE25-13D reads the underlying
            # ``de.capital.fund_classification`` from the inputs dataclass
            # rather than from the persisted derived facts.
            facts_payload = _read_facts(facts_path)
            facts = facts_payload["facts"]

            sale_aggregation = facts["de.derived.per_symbol_sale_aggregation"]
            fund_symbol_gain = sale_aggregation["fund_symbol_gain"]
            source_country = facts["de.derived.source_country_classification"]
            fund_types = source_country["fund_types"]

            # Find a symbol that (a) is classified aktienfonds in the
            # source-country index and (b) has non-zero fund gain so the
            # Teilfreistellung change is numerically observable. The
            # synthetic demo workspace pins at least one such symbol; if
            # a future demo refactor breaks that assumption, the test
            # fails-loud and we update the demo.
            target_symbol = None
            for symbol, gain_str in fund_symbol_gain.items():
                if fund_types.get(symbol) == "aktienfonds":
                    if gain_str not in ("0", "0.00", "0.0", ""):
                        target_symbol = symbol
                        break
            self.assertIsNotNone(
                target_symbol,
                "Demo workspace must contain at least one aktienfonds-classified "
                "fund symbol with non-zero gain so the Teilfreistellung mutation "
                "is observable.",
            )

            # Step 3: mutate the persisted derived-facts artifact.
            fund_types[target_symbol] = "sonstige"
            _write_facts(facts_path, facts_payload)

            # Step 4: re-run Pipeline 2 ONLY — skip Pipeline 1 so the
            # mutation in derived-facts.json survives. Otherwise
            # run_derivation would regenerate the artifact from raw inputs
            # (which still classify the symbol as aktienfonds) and erase
            # the mutation.
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

            # Sanity: the runner saw the skip exactly once.
            self.assertEqual(skipped, ["tax_pipeline.pipelines.y2025.run_derivation"])

            # Step 5: final-legal-output.json must reflect the mutation.
            mutated_final = json.loads(final_path.read_text(encoding="utf-8"))
            mutated_total = _german_capital_total_with_teilfreistellung(mutated_final)
            self.assertNotEqual(
                baseline_total,
                mutated_total,
                "Pipeline 2 must read derived-facts.json from disk: a mutation "
                "to de.derived.source_country_classification.fund_types "
                f"(aktienfonds → sonstige for symbol {target_symbol!r}) should "
                "change the German capital-tax with-Teilfreistellung total via "
                "InvStG § 20. If the totals are equal, Pipeline 2 is ignoring "
                "the persisted boundary state and still re-deriving in memory.",
            )

            # Stronger contract: dropping the Teilfreistellung exemption
            # for a symbol with positive fund gain can only RAISE the tax.
            self.assertGreater(
                _decimal(mutated_total),
                _decimal(baseline_total),
                "Removing aktienfonds Teilfreistellung must raise the German "
                "capital-tax-with-Teilfreistellung total per InvStG § 20.",
            )


def _decimal(value: str):
    from decimal import Decimal

    return Decimal(value)


if __name__ == "__main__":
    unittest.main()
