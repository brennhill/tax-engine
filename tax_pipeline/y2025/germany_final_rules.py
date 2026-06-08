"""Per-stage rule functions for the German final-refund (DE25-22) graph.

This module is the single execution path for ``DE25-22-FINAL-REFUND``,
the headline § 36 Abs. 2 EStG refund stage that consumes outputs from
both the German ordinary and capital rule graphs. Promoting the
computation into a ``LawRule.calculate`` body brings the headline number
inside the audit graph: the ``StageResult`` carries fingerprints for the
four input components and for ``de.final.target_refund_eur``, and the
value appears in ``legal-execution-graph.json`` as a stage output.

WS-4B of ``docs/invariant-migration-plan.md`` replaces the script-level
arithmetic that used to live at
``tax_pipeline/pipelines/y2025/germany_model.py:317-335`` (flagged by
invariants I2 and I5).

Authority:

- § 36 Abs. 2 EStG (Anrechnung der Steuer / Erstattungsbetrag) — the
  controlling refund rule. https://www.gesetze-im-internet.de/estg/__36.html
- § 32d Abs. 1 EStG — the capital tax component netted into the
  final refund. https://www.gesetze-im-internet.de/estg/__32d.html
- InvStG § 20 — the Teilfreistellung-aware capital tax that the
  § 32d(1) component already incorporates.
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
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
from tax_pipeline.y2025.germany_law import q2
from tax_pipeline.y2025.germany_stages import germany_final_law_stages_2025
from tax_pipeline.pipeline_context import set_pipeline_context_value


GERMANY_FINAL_EXECUTION_CONTEXT_KEY = "germany_final_2025.rule_graph_execution"
"""Pipeline-context key under which ``execute_germany_final_rule_graph``
stashes the executed ``RuleGraphExecution`` for in-memory hand-off
(mirrors the per-jurisdiction context keys used by the ordinary /
capital / treaty / U.S. graphs)."""


DE25_22_FINAL_REFUND_STAGE_ID = "DE25-22-FINAL-REFUND"


def de25_22_final_refund(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Compute the headline § 36 Abs. 2 EStG refund.

    Legal authority and ordering:

    - § 36 Abs. 2 EStG fixes the refund balance after every credit
      (Anrechnung) is applied. The German final refund is the
      ordinary-side refund-before-capital netted against the post-treaty
      capital tax, plus the domestic-capital withholding credit.
      https://www.gesetze-im-internet.de/estg/__36.html
    - § 32d Abs. 1 EStG fixes the 25% flat capital tax that flows into
      the netting. The treaty step (DBA-USA Art. 23 routed through
      § 32d Abs. 5 EStG) has already been applied at DE25-20 / DE25-21
      so the capital-tax-with-teilfreistellung-after-treaty value is
      the definitive capital component for § 36 Abs. 2 EStG.
    - InvStG § 20 — Teilfreistellung is already incorporated into the
      capital-tax components passed in.

    Three outputs are produced:
    - ``de.final.refund_before_treaty_eur`` — refund netted against the
      pre-treaty capital tax (intermediate, audit cross-check).
    - ``de.final.chosen_refund_before_domestic_certificate_eur`` —
      refund netted against the post-treaty capital tax, before the
      domestic-capital withholding credit is added (intermediate).
    - ``de.final.target_refund_eur`` — the headline Hauptvordruck
      Erstattung value.
    """
    # § 36 Abs. 2 EStG step 1: ordinary-side refund netted against the
    # pre-treaty capital tax. This is an audit cross-check showing the
    # refund as it would have stood without the DBA-USA Art. 23 / § 32d
    # Abs. 5 treaty step.
    ordinary_refund_before_capital = q2(
        Decimal(str(facts["de.final.ordinary_refund_before_capital_eur"]))
    )
    capital_tax_before_treaty = q2(
        Decimal(
            str(
                facts[
                    "de.final.capital_tax_with_teilfreistellung_before_treaty_eur"
                ]
            )
        )
    )
    capital_tax_after_treaty = q2(
        Decimal(
            str(
                facts[
                    "de.final.capital_tax_with_teilfreistellung_after_treaty_eur"
                ]
            )
        )
    )
    domestic_capital_withholding_credit = q2(
        Decimal(
            str(facts["de.final.domestic_capital_withholding_credit_eur"])
        )
    )
    # § 31 Satz 4 EStG Familienleistungsausgleich routing. The children
    # sub-graph (DE25-CHILDREN-CREDITS) picks Kinderfreibetrag when the
    # § 32 Abs. 6 EStG tariff differential strictly exceeds the BKGG
    # § 6 Abs. 2 Kindergeld received. In that branch the assessment uses
    # the Freibetrag (tax_due drops by ``applied_relief_eur``) AND the
    # Kindergeld already received during the year is hinzugerechnet als
    # Vorauszahlung — so the net refund increment is
    # ``applied_relief_eur − kindergeld_total_eur`` (the marginal benefit
    # of choosing Freibetrag over Kindergeld). When Kindergeld wins
    # (``applied_relief_eur == 0``), the assessment is unchanged and the
    # household keeps the Kindergeld payments outside the refund.
    # https://www.gesetze-im-internet.de/estg/__31.html
    children_applied_relief = q2(
        Decimal(str(facts["de.children.applied_relief_eur"]))
    )
    children_choice = str(facts["de.children.guenstigerpruefung_choice"])
    children_kindergeld_total = q2(
        Decimal(str(facts["de.children.kindergeld_total_eur"]))
    )
    if children_choice == "kinderfreibetrag":
        ordinary_refund_after_children = q2(
            ordinary_refund_before_capital
            + children_applied_relief
            - children_kindergeld_total
        )
    else:
        ordinary_refund_after_children = ordinary_refund_before_capital

    refund_before_treaty = q2(
        ordinary_refund_after_children - capital_tax_before_treaty
    )
    # § 36 Abs. 2 EStG step 2: ordinary-side refund netted against the
    # post-treaty capital tax (the definitive § 32d(1) liability after
    # § 32d(5) and DBA-USA Art. 23 reconciliation).
    chosen_refund_before_domestic_certificate = q2(
        ordinary_refund_after_children - capital_tax_after_treaty
    )
    # § 36 Abs. 2 EStG step 3: add the domestic-capital withholding
    # credit (Kapitalertragsteuer + Soli already withheld at the German
    # bank) to land on the headline Hauptvordruck Erstattung value.
    target_refund = q2(
        chosen_refund_before_domestic_certificate
        + domestic_capital_withholding_credit
    )

    return {
        "de.final.target_refund_eur": target_refund,
        "de.final.refund_before_treaty_eur": refund_before_treaty,
        "de.final.chosen_refund_before_domestic_certificate_eur": (
            chosen_refund_before_domestic_certificate
        ),
        "de.final.ordinary_refund_after_children_eur": (
            ordinary_refund_after_children
        ),
    }


_RULE_FUNCTIONS = {
    DE25_22_FINAL_REFUND_STAGE_ID: de25_22_final_refund,
}


def germany_final_law_rules_2025() -> tuple[LawRule, ...]:
    stages = germany_final_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(
                f"No germany final calculate function registered for {stage.stage_id}"
            )
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def germany_final_initial_facts_2025(
    *,
    ordinary_refund_before_capital_eur: Decimal,
    capital_tax_with_teilfreistellung_before_treaty_eur: Decimal,
    capital_tax_with_teilfreistellung_after_treaty_eur: Decimal,
    domestic_capital_withholding_credit_eur: Decimal,
    children_applied_relief_eur: Decimal,
    children_guenstigerpruefung_choice: str,
    children_kindergeld_total_eur: Decimal,
) -> dict[str, Any]:
    """Assemble the initial-fact dict for ``execute_germany_final_rule_graph``.

    The four ordinary/capital inputs are the refund-before-capital and
    the three capital-side components (pre-treaty tax, post-treaty tax,
    domestic withholding credit). The three children inputs come from
    the executed children sub-graph and route § 31 Satz 4 EStG
    Familienleistungsausgleich into the final settlement: when
    Kinderfreibetrag wins, the tariff differential reduces tax and
    Kindergeld is hinzugerechnet als Vorauszahlung; when Kindergeld
    wins, both children deltas are zero and the final tax is unchanged.
    Each value should be a per-stage q2-quantized EUR amount; the rule
    re-quantizes to match the LawStage rounding policy.
    """
    return {
        "de.final.ordinary_refund_before_capital_eur": (
            ordinary_refund_before_capital_eur
        ),
        "de.final.capital_tax_with_teilfreistellung_before_treaty_eur": (
            capital_tax_with_teilfreistellung_before_treaty_eur
        ),
        "de.final.capital_tax_with_teilfreistellung_after_treaty_eur": (
            capital_tax_with_teilfreistellung_after_treaty_eur
        ),
        "de.final.domestic_capital_withholding_credit_eur": (
            domestic_capital_withholding_credit_eur
        ),
        "de.children.applied_relief_eur": children_applied_relief_eur,
        "de.children.guenstigerpruefung_choice": (
            children_guenstigerpruefung_choice
        ),
        "de.children.kindergeld_total_eur": children_kindergeld_total_eur,
    }


def germany_final_initial_fingerprints_2025(
    initial_facts: Mapping[str, Any],
) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_germany_final_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        germany_final_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(GERMANY_FINAL_EXECUTION_CONTEXT_KEY, execution)
    return execution


__all__ = [
    "DE25_22_FINAL_REFUND_STAGE_ID",
    "GERMANY_FINAL_EXECUTION_CONTEXT_KEY",
    "de25_22_final_refund",
    "execute_germany_final_rule_graph",
    "germany_final_initial_facts_2025",
    "germany_final_initial_fingerprints_2025",
    "germany_final_law_rules_2025",
]
