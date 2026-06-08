"""Test-only helper that materializes ``de.derived.*`` for unit tests.

Production Pipeline 2 code (``y2025/germany_capital_rules.py``) is forbidden
from importing the Pipeline 1 runtime — the Pipeline 1 → Pipeline 2 hand-off
must travel through the on-disk ``derived-facts.json`` artifact (per
``docs/invariant-migration-plan.md`` §1.5; see F-A4 in
``.review/2026-05-01-final/architecture.md``). When ``run_year`` orchestrates
both pipelines the artifact exists; tests that construct
``GermanyCapitalAssessmentInputs2025`` and call
``compute_germany_capital_assessment_2025`` directly do NOT have a workspace
and therefore must inject the derived facts themselves.

This helper runs Pipeline 1 in-memory against the same Pipeline 1 stages
``run_derivation`` runs, and returns the ``de.derived.*`` keys DE25-13
declares as inputs. Importantly, it lives in ``tests/`` — keeping the
in-memory derivation path strictly out of production code so the
two-pipeline boundary stays load-bearing.

Authority: § 32d Abs. 5 EStG per-Posten audit trail
(https://www.gesetze-im-internet.de/estg/__32d.html) and InvStG § 2 Abs. 6
fund taxonomy (https://www.gesetze-im-internet.de/invstg_2018/__2.html)
require the derived-fact shape DE25-13 consumes to match ``run_derivation``
byte-for-byte; the same Pipeline 1 stages are reused here so test inputs
exercise the canonical value graph.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.y2025.derivation.germany_derivations import (
    germany_derivation_law_rules_2025,
)
from tax_pipeline.derivation.runtime import execute_derivation_pipeline
from tax_pipeline.y2025.germany_law import GermanyCapitalAssessmentInputs2025
from tax_pipeline.y2025.germany_capital_rules import (
    _GERMANY_CAPITAL_DERIVED_FACT_KEYS,
)
from tax_pipeline.y2025.germany_children_rules import (
    _GERMANY_CHILDREN_DERIVED_FACT_KEYS,
)


def germany_derived_facts_for_inputs(
    inputs: GermanyCapitalAssessmentInputs2025,
) -> dict[str, Any]:
    """Return the ``de.derived.*`` mapping DE25-13 declares as inputs.

    Synthesizes the Pipeline 1 raw-input contract from the test-supplied
    ``GermanyCapitalAssessmentInputs2025`` and runs the canonical
    ``germany_derivation_law_rules_2025()`` rule graph. Returns only the
    keys listed in ``_GERMANY_CAPITAL_DERIVED_FACT_KEYS`` so tests get
    exactly the boundary surface DE25-13 reads.
    """
    raw_inputs: dict[str, Any] = {
        "de.capital.sale_facts": inputs.sale_facts,
        "de.capital.income_facts": inputs.income_facts,
        "de.capital.bank_certificates": inputs.bank_certificates,
        "de.capital.treaty_dividend_items": inputs.treaty_dividend_items,
        "de.capital.fund_classification": dict(inputs.fund_classification),
        "de.capital.vorabpauschale_inputs": inputs.vorabpauschale_inputs,
        "de.capital.dher_stock_gain": inputs.dher_stock_gain_eur,
        # WS-5B Pipeline 1 raw inputs the derivation graph reads. Tests
        # call this helper without an on-disk fund_classification CSV or
        # operator-supplied manual overrides, so the derivation receives
        # the inputs-dataclass classification verbatim and empty override
        # buckets — matching the canonical ``run_derivation`` shape when
        # no overrides are configured.
        "de.input.repo_fund_classification_csv": dict(inputs.fund_classification),
        "de.input.manual_overrides_fund_types": {},
        "de.input.manual_overrides_aktienfonds_list": [],
        "de.input.manual_overrides_non_aktienfonds_list": [],
        # § 31 EStG / § 32 Abs. 6 EStG / BKGG Pipeline 1 children inputs.
        # Capital-only test fixtures do not exercise the children rule;
        # an empty raw-children tuple aggregates to children_present=False
        # so DERIVE-DE25-CHILDREN runs and produces zero outputs.
        "de.input.children_raw": (),
        "de.input.children_filing_posture": "single",
        # Gap 2 — § 33b Abs. 5 EStG transferral election. Empty
        # children-tuple case never hits the fail-closed guard, so
        # ``None`` (election absent) is safe. The Pipeline 1 derivation
        # downgrades to ``False`` when no qualifying child carries a
        # non-zero §-33b-Abs.-3-EStG Pauschbetrag.
        "de.input.children_disability_pauschbetrag_transfer_election": None,
    }
    derivation = execute_derivation_pipeline(
        raw_inputs,
        germany_derivation_law_rules_2025(),
    )
    return {
        key: derivation.final_facts[key]
        for key in _GERMANY_CAPITAL_DERIVED_FACT_KEYS
        if key in derivation.final_facts
    }


def germany_children_derived_facts_for_empty_household() -> dict[str, Any]:
    """Return the ``de.derived.children_*`` mapping for a no-children household.

    Mirrors :func:`germany_derived_facts_for_inputs` but exercises the
    DERIVE-DE25-CHILDREN Pipeline 1 stage directly with an empty raw-
    children tuple. Returns the four ``de.derived.children_*`` keys
    DE25-CHILDREN-CREDITS declares as inputs.

    Demo-style test fixtures (no qualifying children) reuse this helper
    to inject the boundary state into
    ``compute_germany_children_assessment_2025`` without writing
    ``derived-facts.json`` to disk.

    Authority: § 31 EStG (Familienleistungsausgleich) — when no
    qualifying child is declared, the aggregated facts are
    ``children_present=False`` and all EUR amounts are zero. The
    children sub-graph short-circuits to the same all-zero outputs in
    that branch, so the boundary state only needs to carry the four
    aggregate keys for the input-tracking guard to be satisfied.
    """
    raw_inputs: dict[str, Any] = {
        "de.capital.sale_facts": (),
        "de.capital.income_facts": (),
        "de.capital.bank_certificates": (),
        "de.capital.treaty_dividend_items": (),
        "de.capital.fund_classification": {},
        "de.capital.vorabpauschale_inputs": (),
        "de.capital.dher_stock_gain": Decimal("0"),
        "de.input.repo_fund_classification_csv": {},
        "de.input.manual_overrides_fund_types": {},
        "de.input.manual_overrides_aktienfonds_list": [],
        "de.input.manual_overrides_non_aktienfonds_list": [],
        "de.input.children_raw": (),
        "de.input.children_filing_posture": "single",
        # Gap 2 — § 33b Abs. 5 EStG transferral election. Empty
        # children-tuple case never hits the fail-closed guard, so
        # ``None`` (election absent) is safe. The Pipeline 1 derivation
        # downgrades to ``False`` when no qualifying child carries a
        # non-zero §-33b-Abs.-3-EStG Pauschbetrag.
        "de.input.children_disability_pauschbetrag_transfer_election": None,
    }
    derivation = execute_derivation_pipeline(
        raw_inputs,
        germany_derivation_law_rules_2025(),
    )
    return {
        key: derivation.final_facts[key]
        for key in _GERMANY_CHILDREN_DERIVED_FACT_KEYS
        if key in derivation.final_facts
    }


__all__ = [
    "germany_children_derived_facts_for_empty_household",
    "germany_derived_facts_for_inputs",
]
