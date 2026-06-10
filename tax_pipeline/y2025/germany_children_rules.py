"""Per-stage rule function for the § 31 EStG Familienleistungsausgleich
Günstigerprüfung sub-graph (Wave 11A).

This module is the single execution path for ``DE25-CHILDREN-CREDITS``,
the children sub-graph that picks between Kindergeld retention and
Kinderfreibetrag deduction per § 31 EStG. Children is its own sibling
sub-graph — same shape as ``germany_capital_2025_rules``,
``germany_kap_projection_2025_rules``, and
``germany_guenstigerpruefung_2025_rules`` — because the
Familienleistungsausgleich is a distinct legal pathway and deserves its
own execution scope.

The sub-graph reads the per-child aggregates produced by Pipeline 1
(``DERIVE-DE25-CHILDREN`` writes ``de.derived.children_*`` to
``derived-facts.json``) plus the as-modeled ordinary outputs threaded
in by the executor (zvE, income tax, filing posture from the executed
ordinary sub-graph). It does NOT mutate DE25-07 zvE or DE25-08 tariff —
the chosen relief value is consumed by the final-settlement stage
(DE25-22-FINAL-REFUND) which applies the § 31 Satz 4 EStG netting.

Authority:

- § 31 EStG (Familienleistungsausgleich, Günstigerprüfung):
  https://www.gesetze-im-internet.de/estg/__31.html
- § 32 Abs. 6 EStG (Kinderfreibetrag + BEA-Freibetrag):
  https://www.gesetze-im-internet.de/estg/__32.html
- § 32a Abs. 1 / Abs. 5 EStG (income tariff used for the
  counterfactual): https://www.gesetze-im-internet.de/estg/__32a.html
- BKGG § 6 Abs. 2 (Kindergeld monthly amount):
  https://www.gesetze-im-internet.de/bkgg_1996/
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import (
    LawRule,
    RuleGraphExecution,
    execute_rule_graph,
)
from tax_pipeline.y2025.germany_law import (
    german_income_tax_single_2025,
    german_income_tax_split_2025,
    q2,
)
from tax_pipeline.y2025.germany_stages import germany_children_law_stages_2025
from tax_pipeline.pipeline_context import set_pipeline_context_value


GERMANY_CHILDREN_EXECUTION_CONTEXT_KEY = (
    "germany_children_2025.rule_graph_execution"
)
"""Pipeline-context key under which ``execute_germany_children_rule_graph``
stashes the executed ``RuleGraphExecution`` for in-memory hand-off
(mirrors the per-jurisdiction context keys used by the ordinary /
capital / final / kap / guenstigerpruefung graphs)."""


DE25_CHILDREN_CREDITS_STAGE_ID = "DE25-CHILDREN-CREDITS"
DE25_CHILDREN_DISABILITY_PAUSCHBETRAG_STAGE_ID = (
    "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG"
)


ZERO_EUR = Decimal("0.00")


# ---------------------------------------------------------------------------
# Pipeline 1 → Pipeline 2 boundary helpers
# ---------------------------------------------------------------------------
# Mirrors ``load_germany_capital_derived_facts``: reads ``derived-facts.json``
# and rehydrates the ``de.derived.children_*`` keys DE25-CHILDREN-CREDITS
# declares as inputs. JSON serialization is lossy for Decimals (string)
# and bools (preserved); we restore Decimals here. The
# ``de.derived.children_facts`` aggregate is consumed only as an opaque
# pass-through — the rule body reads the scalar totals, not the per-child
# tuple — so we do not bother rehydrating the tuple-of-Child2025 shape.
#
# Authority: § 31 EStG / § 32 Abs. 6 EStG / BKGG (the boundary state must
# stay byte-stable end-to-end so the audit trail is faithful).


_GERMANY_CHILDREN_DERIVED_FACT_KEYS = (
    "de.derived.children_present",
    "de.derived.children_count",
    "de.derived.kinderfreibetrag_total_eur",
    "de.derived.kindergeld_received_total_eur",
    # Gap 2 — § 33b Abs. 5 EStG transferral. Read by
    # DE25-CHILDREN-DISABILITY-PAUSCHBETRAG (audit-only re-emission).
    "de.derived.children_disability_pauschbetrag_total_eur",
    "de.derived.children_disability_pauschbetrag_transfer_election",
)
"""``de.derived.*`` keys consumed by the children sub-graph.

Listed explicitly (not derived from the rule graph) so adding a new
derivation stage that the children sub-graph does not yet consume
doesn't accidentally pull a stale key into Pipeline 2's initial facts.
"""


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def hydrate_germany_children_derived_facts(
    raw_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Restore canonical Python types for ``de.derived.children_*`` keys.

    JSON round-tripping through :class:`AuditEncoder` flattens Decimals
    to fixed-point strings. Booleans round-trip natively. The
    ``children_count`` value round-trips as an int. The two EUR totals
    round-trip as strings and are restored to Decimals here so the rule
    body can call :func:`q2` / arithmetic against them without surprise.
    """
    out: dict[str, Any] = {}
    if "de.derived.children_present" in raw_facts:
        out["de.derived.children_present"] = bool(
            raw_facts["de.derived.children_present"]
        )
    if "de.derived.children_count" in raw_facts:
        out["de.derived.children_count"] = int(
            raw_facts["de.derived.children_count"]
        )
    if "de.derived.kinderfreibetrag_total_eur" in raw_facts:
        out["de.derived.kinderfreibetrag_total_eur"] = _to_decimal(
            raw_facts["de.derived.kinderfreibetrag_total_eur"]
        )
    if "de.derived.kindergeld_received_total_eur" in raw_facts:
        out["de.derived.kindergeld_received_total_eur"] = _to_decimal(
            raw_facts["de.derived.kindergeld_received_total_eur"]
        )
    # Gap 2 — § 33b Abs. 5 EStG transferral total + election. The
    # transferred total round-trips as a string through AuditEncoder;
    # the election round-trips as a bool natively.
    if "de.derived.children_disability_pauschbetrag_total_eur" in raw_facts:
        out["de.derived.children_disability_pauschbetrag_total_eur"] = (
            _to_decimal(
                raw_facts[
                    "de.derived.children_disability_pauschbetrag_total_eur"
                ]
            )
        )
    if (
        "de.derived.children_disability_pauschbetrag_transfer_election"
        in raw_facts
    ):
        out[
            "de.derived.children_disability_pauschbetrag_transfer_election"
        ] = bool(
            raw_facts[
                "de.derived.children_disability_pauschbetrag_transfer_election"
            ]
        )
    return out


def load_germany_children_derived_facts(paths: Any) -> dict[str, Any]:
    """Load + rehydrate the children ``de.derived.*`` facts from disk.

    Mirrors :func:`load_germany_capital_derived_facts` but for the
    children sub-graph. Used by ``germany_children_initial_facts_2025``
    when no in-memory ``derived_facts`` are supplied. The on-disk
    artifact is the canonical Pipeline 1 → Pipeline 2 boundary per
    ``docs/invariant-migration-plan.md`` §1.5.
    """
    from tax_pipeline.derivation.persistence import load_derivation_facts

    return hydrate_germany_children_derived_facts(load_derivation_facts(paths))


# ---------------------------------------------------------------------------
# Rule body: § 31 EStG Günstigerprüfung
# ---------------------------------------------------------------------------


def de25_children_credits(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Compute the § 31 EStG Familienleistungsausgleich Günstigerprüfung.

    Legal authority and ordering:

    - § 31 EStG (Familienleistungsausgleich): the Finanzamt automatically
      picks the more favorable of (a) Kindergeld retained vs. (b) the
      Kinderfreibetrag + BEA-Freibetrag deduction (Günstigerprüfung).
      https://www.gesetze-im-internet.de/estg/__31.html
    - § 32 Abs. 6 EStG (Kinderfreibetrag + BEA-Freibetrag): the
      €6,672 Kinderfreibetrag plus €2,928 BEA-Freibetrag per child for
      single / married_joint, halved per spouse in married_separate.
      The aggregator already applied the per-spouse split at the
      Pipeline 1 boundary; this rule reads the household total.
      https://www.gesetze-im-internet.de/estg/__32.html
    - BKGG § 6 Abs. 2 (Kindergeld monthly amount): €255/month uniform
      for VZ 2025 (raised from €250 by the Steuerfortentwicklungsgesetz
      2024, effective 01.01.2025).
      https://www.gesetze-im-internet.de/bkgg_1996/
    - § 32a Abs. 1 / Abs. 5 EStG (counterfactual tariff): the
      Kinderfreibetrag deduction reduces zvE before the § 32a tariff
      runs again, so the differential ``tariff(zvE) -
      tariff(zvE - Kinderfreibetrag)`` is the "tax saving" the
      Finanzamt compares against Kindergeld.
      https://www.gesetze-im-internet.de/estg/__32a.html

    Math:

    1. If no qualifying children (children_present=False or count=0),
       all outputs are zero / "kindergeld" pass-through. No § 32 Abs. 6
       comparison runs.
    2. Otherwise, pick the tariff function based on filing posture and
       compute ``tax_at_zve - tax_at_zve_minus_kinderfreibetrag``.
    3. If that differential exceeds Kindergeld received, choose
       Kinderfreibetrag (applied_relief_eur = differential); else
       choose Kindergeld (applied_relief_eur = 0).

    The chosen relief flows to DE25-22-FINAL-REFUND, which applies the
    § 31 Satz 4 EStG netting (subtract differential, hinzurechnen
    Kindergeld) outside this stage. DE25-07 zvE and DE25-08 tariff
    remain unmutated.
    """
    children_present: bool = bool(facts["de.derived.children_present"])
    children_count: int = int(facts["de.derived.children_count"])
    kinderfreibetrag_total = _to_decimal(
        facts["de.derived.kinderfreibetrag_total_eur"]
    )
    kindergeld_total = _to_decimal(
        facts["de.derived.kindergeld_received_total_eur"]
    )
    zve_ordinary = _to_decimal(facts["de.ordinary.taxable_income_eur"])
    income_tax_at_zve = _to_decimal(facts["de.ordinary.income_tax_eur"])
    filing_posture = str(facts["de.ordinary.filing_posture"]).strip().lower()

    if filing_posture not in {"single", "married_joint", "married_separate"}:
        # § 32a EStG — unsupported posture fails closed (CLAUDE.md: never
        # silently default; a posture we cannot tariff is a real defect).
        raise ValueError(
            "Germany § 31 EStG children Günstigerprüfung: unsupported "
            f"filing posture {filing_posture!r}; expected one of "
            "{single, married_joint, married_separate}."
        )

    # Short-circuit when no qualifying child is declared. The household
    # has no Familienleistungsausgleich pathway; the demo workspace
    # without children must produce identical numerics.
    if not children_present or children_count == 0:
        return {
            "de.children.applied_relief_eur": ZERO_EUR,
            "de.children.guenstigerpruefung_choice": "kindergeld",
            "de.children.kinderfreibetrag_total_eur": ZERO_EUR,
            "de.children.kindergeld_total_eur": ZERO_EUR,
            "de.children.kinderfreibetrag_tax_saving_eur": ZERO_EUR,
            "de.children.qualifying_children_count": 0,
        }

    # § 32a Abs. 1 vs. § 32a Abs. 5 EStG — pick the right tariff variant
    # based on filing posture. The counterfactual uses the same tariff
    # family as the ordinary side already does, so the comparison is
    # like-for-like with DE25-08 outputs.
    if filing_posture == "married_joint":
        tariff = german_income_tax_split_2025
    else:
        tariff = german_income_tax_single_2025

    # § 32 Abs. 6 EStG: Kinderfreibetrag reduces zvE before the tariff;
    # below-zero zvE clips to zero (the tariff itself maps to zero for
    # zvE below the Grundfreibetrag, but we clip explicitly to keep the
    # arithmetic shape identical for negative-zvE corner cases).
    counterfactual_zve = zve_ordinary - kinderfreibetrag_total
    if counterfactual_zve < ZERO_EUR:
        counterfactual_zve = ZERO_EUR
    tax_at_counterfactual = q2(tariff(counterfactual_zve))

    # The tariff differential is the § 32 Abs. 6 EStG Steuerersparnis the
    # Finanzamt compares against Kindergeld received. We re-quantize the
    # as-modeled income_tax_at_zve so the differential math is cent-stable.
    tax_at_zve = q2(income_tax_at_zve)
    differential = q2(tax_at_zve - tax_at_counterfactual)
    if differential < ZERO_EUR:
        differential = ZERO_EUR

    # § 31 EStG Satz 1 Günstigerprüfung — choose the more favorable path.
    # Tie-breaker (differential == kindergeld) → Kindergeld retained
    # (the Finanzamt only deducts the Freibetrag when it is *strictly*
    # better than Kindergeld; equal values preserve Kindergeld payments
    # already received during the year).
    if differential > kindergeld_total:
        choice = "kinderfreibetrag"
        applied_relief = differential
    else:
        choice = "kindergeld"
        applied_relief = ZERO_EUR

    return {
        "de.children.applied_relief_eur": applied_relief,
        "de.children.guenstigerpruefung_choice": choice,
        "de.children.kinderfreibetrag_total_eur": q2(kinderfreibetrag_total),
        "de.children.kindergeld_total_eur": q2(kindergeld_total),
        "de.children.kinderfreibetrag_tax_saving_eur": differential,
        "de.children.qualifying_children_count": children_count,
    }


def de25_children_disability_pauschbetrag(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Re-emit the § 33b Abs. 5 EStG transferral total for audit (Gap 2).

    Pipeline 2 audit-only stage in the children sub-graph. Reads the
    Pipeline 1 derived total
    (``de.derived.children_disability_pauschbetrag_total_eur``), the
    children-presence flag, and the profile-level transferral election,
    and emits ``de.children.disability_pauschbetrag_transferred_eur`` —
    the exact same numeric value the ordinary stage
    ``DE25-BEHINDERUNG-PAUSCHBETRAG`` consumes from the same Pipeline 1
    derived fact.

    Two stages produce the same scalar by construction (Pipeline 1
    aggregator output → both consumers): one in the ordinary graph for
    the parents' assessment ordering, one in the children sub-graph
    for the children's audit packet. The ordinary path is the
    legally-effective application of the transferral; the children
    path is the audit/form-rendering surface.

    Gate logic:

    1. If the transferral election is False → emit zero (per § 33b
       Abs. 5 Satz 1 EStG: Pauschbetrag forfeit absent the parents'
       claim).
    2. If no qualifying children are declared → emit zero (no child
       Pauschbetrag exists to transfer).
    3. Otherwise → re-emit the Pipeline 1 derived total.

    Authority:
    - § 33b Abs. 3 EStG (Pauschbetrag schedule by GdB):
      https://www.gesetze-im-internet.de/estg/__33b.html
    - § 33b Abs. 5 EStG (transferral to parents):
      https://www.gesetze-im-internet.de/estg/__33b.html
    """
    children_present: bool = bool(facts["de.derived.children_present"])
    election_active: bool = bool(
        facts["de.derived.children_disability_pauschbetrag_transfer_election"]
    )
    derived_total = _to_decimal(
        facts["de.derived.children_disability_pauschbetrag_total_eur"]
    )

    if not election_active or not children_present:
        # § 33b Abs. 5 Satz 1 EStG: Pauschbetrag attaches to the parents
        # only when claimed. Without the election (or without a
        # qualifying child) no transferral applies and the parents'
        # household total is unchanged.
        return {
            "de.children.disability_pauschbetrag_transferred_eur": ZERO_EUR,
        }

    # Election active and children declared: re-emit the Pipeline 1
    # derivation aggregate. Equality with
    # ``de.derived.children_disability_pauschbetrag_total_eur`` is part
    # of the audit contract (see DE25-CHILDREN-DISABILITY-PAUSCHBETRAG
    # law_order_note in germany_2025_stages.py).
    if derived_total < ZERO_EUR:
        # Defensive guard — the aggregator quantizes at q2 and the
        # schedule is non-negative, so a negative value here would
        # signal upstream corruption rather than a legitimate state.
        raise ValueError(
            "§ 33b Abs. 5 EStG transferral total cannot be negative; "
            f"got {derived_total!r}."
        )
    return {
        "de.children.disability_pauschbetrag_transferred_eur": q2(derived_total),
    }


_RULE_FUNCTIONS = {
    DE25_CHILDREN_CREDITS_STAGE_ID: de25_children_credits,
    DE25_CHILDREN_DISABILITY_PAUSCHBETRAG_STAGE_ID: (
        de25_children_disability_pauschbetrag
    ),
}


def germany_children_law_rules_2025() -> tuple[LawRule, ...]:
    stages = germany_children_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(
                f"No germany children calculate function registered for {stage.stage_id}"
            )
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def germany_children_initial_facts_2025(
    *,
    derived_facts: Mapping[str, Any] | None = None,
    ordinary_taxable_income_eur: Decimal,
    ordinary_income_tax_eur: Decimal,
    filing_posture: str,
) -> dict[str, Any]:
    """Assemble the initial-fact dict for the children sub-graph.

    Reads the four ``de.derived.*`` aggregates from the persisted
    ``derived-facts.json`` (or from an in-memory ``derived_facts``
    mapping for tests that bypass ``run_year``) and threads the three
    ordinary outputs (zvE, income tax, filing posture) through.

    Authority: § 31 EStG / § 32 Abs. 6 EStG / BKGG. The on-disk
    derivation artifact is the canonical Pipeline 1 → Pipeline 2
    boundary per ``docs/invariant-migration-plan.md`` §1.5.

    Fail-closed: when no in-memory ``derived_facts`` is supplied and
    no ``derived-facts.json`` is available, raises FileNotFoundError —
    the children pathway needs the Pipeline 1 aggregates and silently
    re-deriving them in Pipeline 2 would weaken the audit boundary.
    """
    if derived_facts is not None:
        derived = hydrate_germany_children_derived_facts(derived_facts)
    else:
        loaded = _load_persisted_germany_children_derived_facts()
        if loaded is None:
            from pathlib import Path

            from tax_pipeline.derivation.persistence import (
                derivation_facts_path,
            )
            from tax_pipeline.year_runtime import active_year_paths
            try:
                paths = active_year_paths(Path(__file__), default_year=2025)
                expected_path = derivation_facts_path(paths)
                location_hint = f" at {expected_path}"
            except Exception:
                location_hint = ""
            raise FileNotFoundError(
                f"derived-facts.json not found{location_hint}. "
                f"Pipeline 1 (Derivation) must run before Pipeline 2 "
                f"(children sub-graph). Run "
                f"`python -m tax_pipeline.pipelines.y2025.run_derivation` "
                f"first, or pass derived_facts= to inject the boundary "
                f"state directly (test scenarios)."
            )
        derived = loaded

    # Restrict to the keys declared as inputs by the children sub-graph
    # stages (DE25-CHILDREN-CREDITS plus, post-Gap-2,
    # DE25-CHILDREN-DISABILITY-PAUSCHBETRAG); extra keys would be
    # flagged by the executor's input-tracking guard (invariant I7).
    children_facts = {
        key: derived[key]
        for key in _GERMANY_CHILDREN_DERIVED_FACT_KEYS
        if key in derived
    }
    children_facts["de.ordinary.taxable_income_eur"] = ordinary_taxable_income_eur
    children_facts["de.ordinary.income_tax_eur"] = ordinary_income_tax_eur
    children_facts["de.ordinary.filing_posture"] = filing_posture
    return children_facts


def _load_persisted_germany_children_derived_facts() -> dict[str, Any] | None:
    """Load ``de.derived.children_*`` from the active workspace's disk artifact.

    Mirrors ``germany_capital_2025_rules._load_persisted_germany_derived_facts``:
    returns ``None`` when no workspace is resolvable (so test callers
    that did not pass ``derived_facts=`` get a fail-closed error from
    the caller) and otherwise returns the rehydrated children boundary.
    """
    import os
    import sys
    from pathlib import Path

    from tax_pipeline.derivation.persistence import (
        derivation_facts_path,
    )
    from tax_pipeline.year_runtime import active_year_paths

    if not os.environ.get("TAX_WORKSPACE_ROOT") and not os.environ.get("TAX_PROJECT_ROOT"):
        return None

    try:
        paths = active_year_paths(Path(__file__), default_year=2025)
    except Exception:
        return None

    facts_path = derivation_facts_path(paths)
    if not facts_path.exists():
        return None

    print(
        f"[germany_children] reading de.derived.children_* from {facts_path}",
        file=sys.stderr,
    )
    return load_germany_children_derived_facts(paths)


def germany_children_initial_fingerprints_2025(
    initial_facts: Mapping[str, Any],
) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_germany_children_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        germany_children_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(
        GERMANY_CHILDREN_EXECUTION_CONTEXT_KEY, execution
    )
    return execution


__all__ = [
    "DE25_CHILDREN_CREDITS_STAGE_ID",
    "DE25_CHILDREN_DISABILITY_PAUSCHBETRAG_STAGE_ID",
    "GERMANY_CHILDREN_EXECUTION_CONTEXT_KEY",
    "de25_children_credits",
    "de25_children_disability_pauschbetrag",
    "execute_germany_children_rule_graph",
    "germany_children_initial_facts_2025",
    "germany_children_initial_fingerprints_2025",
    "germany_children_law_rules_2025",
    "hydrate_germany_children_derived_facts",
    "load_germany_children_derived_facts",
]
