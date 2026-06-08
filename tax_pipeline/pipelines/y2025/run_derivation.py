"""Pipeline 1 (Derivation) entry-point module for tax year 2025.

Runs BEFORE ``germany_model`` / ``us_model`` in ``run_year.py``'s
pipeline-module list (see ``docs/invariant-migration-plan.md`` §1.5).
Reads workspace inputs, builds Pipeline 1 initial facts, executes the
derivation rule graph, and persists the results to
``derived-facts.json`` + ``derivation-graph.json`` under
``paths.derivation_root``.

WS-5H lands this module with EMPTY initial facts and an EMPTY rule
set. WS-5B (this commit) registers the first concrete stage,
``DERIVE-DE25-FUND-CLASSIFICATION``, and seeds Pipeline 1 initial
facts with the four InvStG § 2 Abs. 6 fund-classification inputs
(engine-shipped repo CSV plus three workspace-level override
buckets). WS-5A will extend the initial-facts builder with the raw
DE25-13 broker / 1099 / bank-certificate inputs.

Authority context: this entry-point is engine-internal infrastructure
that supports the same audit-trail integrity as Pipeline 2's
``write_final_legal_output_2025``. Per § 32d Abs. 5 EStG (per-Posten
audit trail, https://www.gesetze-im-internet.de/estg/__32d.html) and
InvStG § 2 Abs. 6 (fund taxonomy,
https://www.gesetze-im-internet.de/invstg_2018/__2.html) the derived
facts are first-class audit objects.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tax_pipeline.derivation import (
    DERIVATION_FACTS_NAME,
    DERIVATION_GRAPH_NAME,
    execute_derivation_pipeline,
    germany_derivation_law_rules_2025,
    usa_derivation_law_rules_2025,
    write_derivation_artifacts,
)
from tax_pipeline.y2025.derivation.germany_derivations import (
    CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY,
    CHILDREN_INPUT_FILING_POSTURE_KEY,
    CHILDREN_INPUT_RAW_KEY,
    FUND_CLASSIFICATION_INPUT_AKTIENFONDS,
    FUND_CLASSIFICATION_INPUT_FUND_TYPES,
    FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS,
    FUND_CLASSIFICATION_INPUT_REPO_CSV,
)
from tax_pipeline.derivation.runtime import DerivationPipelineResult
from tax_pipeline.fund_classification_data import (
    load_repo_german_fund_classification,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.year_runtime import active_year_paths


def build_initial_facts_2025(paths: YearPaths) -> dict[str, Any]:
    """Build the Pipeline 1 initial facts dict for the 2025 year.

    Loads BOTH:

    - WS-5A's raw broker / 1099 / bank-certificate / DHER /
      fund-classification facts feeding the 5 DE25-13 derivation stages.
    - WS-5B's four fund-classification source streams (repo CSV + three
      workspace overrides) feeding ``DERIVE-DE25-FUND-CLASSIFICATION``.

    Authority context: § 20 Abs. 4 EStG cost-basis aggregation,
    § 43a Abs. 3 EStG bank-certificate aggregation, § 32d Abs. 5 EStG
    per-Posten foreign-tax indexing, InvStG § 2 Abs. 6 fund-type
    taxonomy. Loading them at the Pipeline 1 boundary (rather than
    inside Pipeline 2 stage calculate bodies) is what makes Pipeline
    1's audit graph distinguishable from Pipeline 2's legal graph.
    """
    # Local import to avoid circular module pulls during package init —
    # ``germany_loaders`` transitively imports things that don't need to
    # land at module-top-of-file time.
    from tax_pipeline.pipelines.y2025 import germany_loaders as _germany_loaders
    from tax_pipeline.pipelines.y2025.germany_loaders import (
        load_bank_capital_certificates_2025,
        load_capital_income_facts_2025,
        load_capital_sale_facts_2025,
        load_dher_results,
        load_fund_classification,
        load_vorabpauschale_inputs_2025,
    )
    # § 31 EStG / § 32 Abs. 6 EStG / BKGG — children inputs feeding
    # DERIVE-DE25-CHILDREN. Imported here (not at module top) to keep
    # the same lazy-import discipline as the other germany_loaders.
    from tax_pipeline.y2025.germany_inputs import _load_children_2025

    _germany_loaders.reset_year_paths()

    # WS-5A raw facts
    sale_facts = load_capital_sale_facts_2025()
    income_facts = load_capital_income_facts_2025()
    bank_certificates = load_bank_capital_certificates_2025()
    dher = load_dher_results()
    fund_classification = load_fund_classification()
    vorabpauschale_inputs = load_vorabpauschale_inputs_2025()
    if "total_gain_eur" not in dher:
        raise ValueError(
            "Germany derivation pipeline: dher-results.json missing "
            "'total_gain_eur'; cannot derive per-symbol sale aggregation."
        )

    # WS-5B fund-classification raw inputs
    repo_csv = load_repo_german_fund_classification()
    overrides_path = paths.manual_overrides_path
    if overrides_path.exists():
        configured = json.loads(
            overrides_path.read_text(encoding="utf-8")
        ).get("fund_classification", {})
    else:
        configured = {}
    fund_types = configured.get("fund_types", {})
    aktienfonds_list = configured.get("aktienfonds", [])
    non_aktienfonds_list = configured.get("non_aktienfonds", [])

    # § 31 EStG Familienleistungsausgleich children — raw rows from
    # config/children.csv. Filing posture is read from profile.json
    # so DERIVE-DE25-CHILDREN can apply the § 32 Abs. 6 Satz 1/2 EStG
    # split-vs-combined rule.
    children_raw = _load_children_2025(paths)
    if paths.profile_path.exists():
        profile_obj = json.loads(
            paths.profile_path.read_text(encoding="utf-8")
        )
    else:
        profile_obj = {}
    raw_filing_posture = (
        str(
            profile_obj.get("jurisdictions", {})
            .get("germany", {})
            .get("filing_posture", "")
        )
        .strip()
        .lower()
    )
    if raw_filing_posture not in {"single", "married_joint", "married_separate"}:
        # Workspaces with no children declared do not need a children-
        # specific posture. The Pipeline 2 short-circuit relies on
        # children_present=False; supplying ``single`` here keeps the
        # § 32 Abs. 6 EStG aggregator legal even on bare workspaces.
        raw_filing_posture = "single"

    # § 33b Abs. 5 EStG transferral election. Profile-level boolean read
    # from ``elections.germany_disability_pauschbetrag_transfer``. ``None``
    # signals "election absent" — the Pipeline 1 derivation fails closed
    # if any qualifying child carries a non-zero §-33b-Abs.-3-EStG
    # Pauschbetrag (so the engine cannot silently choose between
    # transferral and forfeiture).
    elections_obj = profile_obj.get("elections") or {}
    raw_election = elections_obj.get(
        "germany_disability_pauschbetrag_transfer", None
    )
    if raw_election is None:
        disability_transfer_election: bool | None = None
    elif isinstance(raw_election, bool):
        disability_transfer_election = raw_election
    else:
        raise ValueError(
            "elections.germany_disability_pauschbetrag_transfer must be "
            f"true, false, or omitted; got {raw_election!r}. "
            "Authority: § 33b Abs. 5 EStG "
            "(https://www.gesetze-im-internet.de/estg/__33b.html)."
        )

    return {
        # WS-5A inputs (DE25-13 derivations consume these)
        "de.capital.sale_facts": sale_facts,
        "de.capital.income_facts": income_facts,
        "de.capital.bank_certificates": bank_certificates,
        "de.capital.fund_classification": fund_classification,
        "de.capital.dher_stock_gain": dher["total_gain_eur"],
        # InvStG § 19 Vorabpauschale per-fund raw inputs (DE25-13F derivation
        # consumes these; legal stage DE25-13F-VORABPAUSCHALE downstream).
        "de.capital.vorabpauschale_inputs": vorabpauschale_inputs,
        # WS-5B inputs (DERIVE-DE25-FUND-CLASSIFICATION consumes these)
        FUND_CLASSIFICATION_INPUT_REPO_CSV: repo_csv,
        FUND_CLASSIFICATION_INPUT_FUND_TYPES: fund_types,
        FUND_CLASSIFICATION_INPUT_AKTIENFONDS: aktienfonds_list,
        FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS: non_aktienfonds_list,
        # § 31 EStG / § 32 Abs. 6 EStG / BKGG — DERIVE-DE25-CHILDREN inputs.
        CHILDREN_INPUT_RAW_KEY: children_raw,
        CHILDREN_INPUT_FILING_POSTURE_KEY: raw_filing_posture,
        # § 33b Abs. 5 EStG transferral election — profile-level bool or
        # None when omitted. Pipeline 1 fails closed if any qualifying
        # child carries a non-zero §-33b-Abs.-3-EStG Pauschbetrag and
        # the election is None.
        CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY: (
            disability_transfer_election
        ),
    }


def derivation_rules_2025() -> tuple:
    """Concatenate the German + U.S. Pipeline 1 rule sets for 2025.

    Empty until WS-5A / WS-5B register concrete stages. Returning a
    tuple keeps the contract symmetrical with ``germany_law_rules_2025``
    / ``us_law_rules_2025`` in Pipeline 2.
    """
    return germany_derivation_law_rules_2025() + usa_derivation_law_rules_2025()


def run_derivation_pipeline_2025(paths: YearPaths) -> DerivationPipelineResult:
    """Execute Pipeline 1 for the resolved workspace and persist the artifacts.

    Returns the :class:`DerivationPipelineResult` for callers that
    want the in-memory shape (e.g., the reproducibility test).
    """
    initial_facts = build_initial_facts_2025(paths)
    rules = derivation_rules_2025()
    result = execute_derivation_pipeline(initial_facts, rules)
    write_derivation_artifacts(paths, result)
    return result


def main() -> None:
    """``runpy.run_module`` entry point.

    ``run_year.py`` invokes this module via ``runpy`` like the other
    pipeline modules. Resolves the active workspace via
    ``active_year_paths`` (so the same ``TAX_*`` env vars used by
    ``germany_model`` / ``us_model`` apply here).
    """
    paths = active_year_paths(Path(__file__), default_year=2025)
    paths.ensure_directories()
    run_derivation_pipeline_2025(paths)
    facts_relative = (paths.derivation_root / DERIVATION_FACTS_NAME).relative_to(
        paths.workspace_root
    )
    graph_relative = (paths.derivation_root / DERIVATION_GRAPH_NAME).relative_to(
        paths.workspace_root
    )
    print(f"Wrote derivation artifacts → {facts_relative} + {graph_relative}")


if __name__ == "__main__":
    main()
