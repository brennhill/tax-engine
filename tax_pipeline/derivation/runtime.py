"""Pipeline 1 orchestrator (`execute_derivation_pipeline`).

Wraps :func:`tax_pipeline.core.stages.execute_rule_graph` so the
existing tracking-dict (invariant I7), input/output declarations
(invariants I7/I8), and stable fingerprinting (invariant I6) plumbing
applies uniformly to derivation stages. Pipeline 1 produces
deterministic, typed canonical derived facts; no legal interpretation
runs here.

Authority context: this is engine-internal infrastructure that
preserves audit-trail integrity per § 32d Abs. 5 EStG (per-Posten
foreign-tax credit audit trail) by ensuring derived facts trace to
a Pipeline 1 ``StageResult.output_fingerprint`` chain just as legal
outputs trace to Pipeline 2 fingerprints.
https://www.gesetze-im-internet.de/estg/__32d.html

WS-5H lands this orchestrator with an EMPTY rule set. The
``RuleGraphExecution`` shape requires at least one rule, so the empty
case short-circuits to a synthetic, no-stage execution that still
produces a valid ``derivation-graph.json`` (zero nodes, zero edges)
and ``derived-facts.json`` containing only the supplied initial
facts. WS-5A and WS-5B register concrete derivation stages on top of
this scaffold.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tax_pipeline.core.stages import (
    LawRule,
    RuleGraphExecution,
    StageGraphValidation,
    execute_rule_graph,
)


@dataclass(frozen=True)
class DerivationPipelineResult:
    """The outcome of a Pipeline 1 run.

    ``execution`` is the underlying :class:`RuleGraphExecution` when at
    least one derivation stage is registered; ``None`` when the
    Pipeline 1 stage set is empty (the WS-5H framework-only landing).

    ``final_facts`` is the dict of derived facts available to Pipeline
    2 (initial facts + every stage's outputs). For the empty
    Pipeline 1 it equals ``initial_facts`` verbatim.

    ``graph_dict`` is the JSON-serializable audit-graph payload (same
    shape as ``legal-execution-graph.json``) that
    :func:`write_derivation_artifacts` persists to
    ``derivation-graph.json``.
    """

    execution: RuleGraphExecution | None
    final_facts: dict[str, Any]
    graph_dict: dict[str, Any]


def _empty_graph_dict(initial_fact_keys: Sequence[str]) -> dict[str, Any]:
    """Build the audit-graph payload for an empty Pipeline 1 run.

    Mirrors the shape produced by
    :meth:`RuleGraphExecution.to_graph_dict` so the persisted
    ``derivation-graph.json`` has a stable schema regardless of
    whether any stages are registered. Pipeline 2 / audit tooling can
    rely on the same key set in both modes.
    """
    return {
        "schema_version": 1,
        "stage_ids": [],
        "initial_fact_keys": sorted(initial_fact_keys),
        "output_keys": [],
        "nodes": [],
        "edges": [],
    }


def execute_derivation_pipeline(
    initial_facts: Mapping[str, Any],
    rules: Sequence[LawRule],
    *,
    initial_fingerprints: Mapping[str, str] | None = None,
) -> DerivationPipelineResult:
    """Run the Pipeline 1 (Derivation) rule graph.

    ``rules`` may be empty: WS-5H lands an empty Pipeline 1 framework
    that WS-5A and WS-5B populate. When empty, the function returns a
    :class:`DerivationPipelineResult` whose ``execution`` is ``None``
    and whose ``final_facts`` / ``graph_dict`` reflect the no-stage
    boundary contract.

    When ``rules`` is non-empty, the underlying
    :func:`execute_rule_graph` runs unchanged: invariants I6 (canonical
    fingerprints), I7 (declared-input tracking), I8
    (declared-output enforcement) all apply. Pipeline 1 stages must
    use ``DERIVE-`` stage IDs and reuse :class:`LawStage` with empty
    ``form_line_refs`` (the ``OutputDeclaration`` carries an
    ``AuditWaypoint`` such as ``PER_POSTEN_AGGREGATION`` instead).
    """
    rule_tuple = tuple(rules)
    fact_dict = dict(initial_facts)
    if not rule_tuple:
        # The empty-Pipeline-1 case (WS-5H landing). ``execute_rule_graph``
        # rejects empty ``rules`` AND empty ``initial_facts`` because every
        # legal-pipeline run has at least one stage and one fact. Here the
        # framework legitimately has neither yet.
        return DerivationPipelineResult(
            execution=None,
            final_facts=fact_dict,
            graph_dict=_empty_graph_dict(fact_dict.keys()),
        )

    # Non-empty Pipeline 1. Delegate to the shared executor so
    # tracking-dict / fingerprint / declaration-validation behavior is
    # IDENTICAL between the two pipelines.
    if not fact_dict:
        # ``execute_rule_graph`` requires a non-empty initial-facts mapping.
        # If a caller registered stages but supplied no inputs, raise the
        # same error the executor would, with a Pipeline 1-flavored message
        # so the caller knows where to look.
        raise ValueError(
            "execute_derivation_pipeline: initial_facts must be non-empty "
            "when at least one derivation rule is registered"
        )
    execution = execute_rule_graph(
        fact_dict,
        rule_tuple,
        initial_fingerprints=initial_fingerprints,
    )
    return DerivationPipelineResult(
        execution=execution,
        final_facts=dict(execution.final_facts),
        graph_dict=execution.to_graph_dict(),
    )


__all__ = [
    "DerivationPipelineResult",
    "StageGraphValidation",  # re-exported for callers that introspect graph state
    "execute_derivation_pipeline",
]
