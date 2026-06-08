"""Per-stage rule function for the audit-only § 32d Abs. 6 EStG
Günstigerprüfung shadow comparison (F-DE-2).

This module is the single execution path for
``DE25-GUENSTIGERPRUEFUNG-SHADOW``, an audit-only stage that compares
the modeled § 32d Abs. 1 path (25 % flat capital tax) against the
shadow § 32a path (ordinary tariff applied to combined ordinary + capital
income, the election under § 32d Abs. 6 EStG). The stage's outputs are
audit-only (``de.audit.*``); they do NOT feed the final refund. The
purpose is to surface a warning when the taxpayer would benefit from
electing § 32a — today the engine fails closed when the election is
requested (see ``ensure_capital_guenstigerpruefung_position_2025`` in
``tax_pipeline/pipelines/y2025/germany_model.py``), but it gave no
signal that the election would be favorable.

Authority:

- § 32d Abs. 6 EStG (Antragsveranlagung — election to apply the § 32a
  tariff to capital income when it produces a lower tax):
  https://www.gesetze-im-internet.de/estg/__32d.html
- § 32d Abs. 1 EStG (the 25 % flat capital tax this election competes
  against): https://www.gesetze-im-internet.de/estg/__32d.html
- § 32a Abs. 1 EStG (ordinary basic tariff applied under the election):
  https://www.gesetze-im-internet.de/estg/__32a.html
- § 32a Abs. 5 EStG (joint splitting tariff): same URL.
- § 32d Abs. 5 EStG (foreign-tax credit; carries through under the
  § 32a election): https://www.gesetze-im-internet.de/estg/__32d.html
- BMF-Schreiben Abgeltungsteuer 14.05.2025 (Einzelfragen — Günstigerprüfung
  mechanics): https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=6
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
    GUENSTIGERPRUEFUNG_MATERIALITY_EUR,
    german_income_tax_single_2025,
    german_income_tax_split_2025,
    q2,
)
from tax_pipeline.y2025.germany_stages import (
    germany_guenstigerpruefung_law_stages_2025,
)
from tax_pipeline.pipeline_context import set_pipeline_context_value


GERMANY_GUENSTIGERPRUEFUNG_EXECUTION_CONTEXT_KEY = (
    "germany_guenstigerpruefung_2025.rule_graph_execution"
)
"""Pipeline-context key under which
``execute_germany_guenstigerpruefung_rule_graph`` stashes the executed
``RuleGraphExecution`` for in-memory hand-off."""


DE25_GUENSTIGERPRUEFUNG_SHADOW_STAGE_ID = "DE25-GUENSTIGERPRUEFUNG-SHADOW"


ZERO_EUR = Decimal("0.00")
ONE_FLAG = Decimal("1")
ZERO_FLAG = Decimal("0")


def de25_guenstigerpruefung_shadow(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Compute the audit-only § 32d Abs. 6 EStG shadow comparison.

    Inputs (declared on the stage):

    - ``de.audit.guenstiger.zve_ordinary_eur`` — the modeled
      ``de.ordinary.joint_taxable_income`` (zu versteuerndes Einkommen)
      under the actual filing posture. § 2 Abs. 5 EStG.
    - ``de.audit.guenstiger.capital_taxable_after_teilfreistellung_eur``
      — the modeled § 20 Abs. 9 EStG capital base after Teilfreistellung
      and Sparer-Pauschbetrag (``de.capital.taxable_after_allowance.taxable_after_teilfreistellung``).
    - ``de.audit.guenstiger.status_quo_total_tax_eur`` — the modeled
      § 32d Abs. 1 + Abs. 5 + SolzG capital tax (the post-treaty
      ``de.capital.final_tax`` value). This is the capital-side
      delta-from-ordinary the election would replace.
    - ``de.audit.guenstiger.foreign_tax_credit_applied_eur`` — the
      § 32d Abs. 5 EStG credit already applied under the status-quo
      path. Under the § 32d Abs. 6 election the same credit is allowed
      against ordinary tax (§ 32d Abs. 5 reads through), so we subtract
      it from the shadow ordinary-tariff increase.
    - ``de.audit.guenstiger.filing_posture`` — string; selects the
      § 32a Abs. 1 vs. § 32a Abs. 5 tariff variant.

    Math (audit-only — does NOT feed final refund):

    1. ordinary_only_tax = tariff(zvE_ordinary)
    2. shadow_combined_tax = tariff(zvE_ordinary + capital_after_teilfreistellung)
    3. shadow_capital_increment = max(0, shadow_combined_tax - ordinary_only_tax
       - foreign_tax_credit_applied)
    4. diff = status_quo_total_tax - shadow_capital_increment
    5. election_recommended = (diff > GUENSTIGERPRUEFUNG_MATERIALITY_EUR)

    The diff is positive when § 32a would produce less capital-side tax
    than § 32d Abs. 1 — i.e. the taxpayer should elect under § 32d
    Abs. 6 EStG. The magnitude is "how much tax saved if the election
    were filed."
    """
    # § 2 Abs. 5 EStG zu versteuerndes Einkommen — input from
    # DE25-07-TAXABLE-INCOME via the orchestrator.
    zve_ordinary = q2(Decimal(str(facts["de.audit.guenstiger.zve_ordinary_eur"])))
    # § 20 Abs. 9 / InvStG § 20 capital base — input from DE25-16
    # (taxable_after_allowance.taxable_after_teilfreistellung).
    capital_taxable = q2(
        Decimal(
            str(
                facts[
                    "de.audit.guenstiger.capital_taxable_after_teilfreistellung_eur"
                ]
            )
        )
    )
    # § 32d Abs. 1 + Abs. 5 + SolzG capital tax under the status quo —
    # input from DE25-21 (de.capital.final_tax).
    status_quo_total_tax = q2(
        Decimal(str(facts["de.audit.guenstiger.status_quo_total_tax_eur"]))
    )
    # § 32d Abs. 5 EStG creditable foreign tax already applied under
    # § 32d Abs. 1; under the § 32d Abs. 6 election this credit reads
    # through to the § 32a path (Pub. 514-style cross-border ordering is
    # preserved). Source: DE25-18.
    foreign_tax_credit_applied = q2(
        Decimal(
            str(facts["de.audit.guenstiger.foreign_tax_credit_applied_eur"])
        )
    )
    filing_posture = str(facts["de.audit.guenstiger.filing_posture"]).strip().lower()

    # § 32a Abs. 1 vs. § 32a Abs. 5 EStG: pick the right tariff based on
    # the actual filing posture. The shadow uses the same tariff family
    # as the ordinary side already does, so the comparison is
    # like-for-like.
    if filing_posture == "married_joint":
        tariff = german_income_tax_split_2025
    elif filing_posture in {"single", "married_separate"}:
        tariff = german_income_tax_single_2025
    else:
        # § 32a EStG — unsupported postures fail closed per CLAUDE.md
        # (we cannot silently default to a tariff variant).
        raise ValueError(
            "Germany § 32d Abs. 6 Günstigerprüfung shadow: unsupported "
            f"filing posture {filing_posture!r}; expected one of "
            "{single, married_joint, married_separate}."
        )

    # Status-quo ordinary tariff component: the modeled ordinary-only
    # tax that already counts inside the rest of the ordinary refund
    # path. We subtract it from shadow_combined_tax so the shadow
    # increment captures only the *capital* delta under the election.
    ordinary_only_tax = q2(tariff(zve_ordinary))
    shadow_combined_tax = q2(tariff(zve_ordinary + capital_taxable))
    # § 32d Abs. 6 EStG election: the § 32a tariff is applied to the
    # combined base; § 32d Abs. 5 EStG foreign-tax credit reads through.
    # The shadow capital-side increment is what the taxpayer would owe
    # in addition to the ordinary tariff under the election.
    shadow_capital_increment = q2(
        max(
            ZERO_EUR,
            shadow_combined_tax - ordinary_only_tax - foreign_tax_credit_applied,
        )
    )
    # diff > 0  ⇒  § 32a path would tax capital LESS than § 32d(1).
    # diff < 0  ⇒  § 32d(1) is already cheaper, election would be worse.
    diff = q2(status_quo_total_tax - shadow_capital_increment)

    # Materiality threshold: any diff above €10 is structurally
    # actionable; below €10 it is dominated by floor_euro / q2 rounding
    # across the multi-stage path. See germany_2025_law.py for rationale.
    if diff > GUENSTIGERPRUEFUNG_MATERIALITY_EUR:
        election_recommended = ONE_FLAG
    else:
        election_recommended = ZERO_FLAG

    return {
        "de.audit.guenstigerpruefung_shadow_diff_eur": diff,
        "de.audit.guenstigerpruefung_election_recommended": election_recommended,
    }


_RULE_FUNCTIONS = {
    DE25_GUENSTIGERPRUEFUNG_SHADOW_STAGE_ID: de25_guenstigerpruefung_shadow,
}


def germany_guenstigerpruefung_law_rules_2025() -> tuple[LawRule, ...]:
    stages = germany_guenstigerpruefung_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(
                f"No germany Günstigerprüfung calculate function registered for {stage.stage_id}"
            )
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def germany_guenstigerpruefung_initial_facts_2025(
    *,
    zve_ordinary_eur: Decimal,
    capital_taxable_after_teilfreistellung_eur: Decimal,
    status_quo_total_tax_eur: Decimal,
    foreign_tax_credit_applied_eur: Decimal,
    filing_posture: str,
) -> dict[str, Any]:
    """Assemble the initial-fact dict for
    ``execute_germany_guenstigerpruefung_rule_graph``.

    The five inputs are everything the audit-only shadow comparison
    needs to compute the § 32d Abs. 6 vs. § 32d Abs. 1 delta. Each
    EUR amount should be q2-quantized at the call site; the rule body
    re-quantizes defensively.
    """
    return {
        "de.audit.guenstiger.zve_ordinary_eur": zve_ordinary_eur,
        "de.audit.guenstiger.capital_taxable_after_teilfreistellung_eur": (
            capital_taxable_after_teilfreistellung_eur
        ),
        "de.audit.guenstiger.status_quo_total_tax_eur": status_quo_total_tax_eur,
        "de.audit.guenstiger.foreign_tax_credit_applied_eur": (
            foreign_tax_credit_applied_eur
        ),
        "de.audit.guenstiger.filing_posture": filing_posture,
    }


def germany_guenstigerpruefung_initial_fingerprints_2025(
    initial_facts: Mapping[str, Any],
) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_germany_guenstigerpruefung_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        germany_guenstigerpruefung_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(
        GERMANY_GUENSTIGERPRUEFUNG_EXECUTION_CONTEXT_KEY, execution
    )
    return execution


__all__ = [
    "DE25_GUENSTIGERPRUEFUNG_SHADOW_STAGE_ID",
    "GERMANY_GUENSTIGERPRUEFUNG_EXECUTION_CONTEXT_KEY",
    "de25_guenstigerpruefung_shadow",
    "execute_germany_guenstigerpruefung_rule_graph",
    "germany_guenstigerpruefung_initial_facts_2025",
    "germany_guenstigerpruefung_initial_fingerprints_2025",
    "germany_guenstigerpruefung_law_rules_2025",
]
