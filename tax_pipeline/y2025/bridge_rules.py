"""Per-stage rule functions for the cross-jurisdiction (BRIDGE-2025) graph.

This module is the single execution path for the declared
``BRIDGE25-*`` LawStages. The first stage,
``BRIDGE25-FOREIGN-TAX-RECONCILIATION``, replaces the script-level
foreign-tax reconciliation block in ``germany_model.py:259-269`` (flagged
by invariants I2 and I5 of ``docs/invariant-migration-plan.md``). Moving
the assertion into a ``LawRule.calculate`` body brings the legal value
inside the audit graph: the executed ``StageResult`` carries fingerprints
for both the four input components and the verified total, and a
violation surfaces as a typed ``LegalInvariantViolation`` rather than as
a script-level ``ValueError``.

Authority:

- § 32d Abs. 5 EStG (per-Posten foreign-tax credit) — the foreign-tax
  basis must reconcile to the per-item totals consumed by the § 32d(5)
  cap. https://www.gesetze-im-internet.de/estg/__32d.html
- 26 U.S.C. § 901 — IRS foreign tax credit; a verifiable foreign-tax
  amount is the credit basis on Form 1116.
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
- DBA-USA Art. 23 — residence-state credit ties the U.S. and German
  foreign-tax-credit chains across jurisdictions.
  https://www.irs.gov/pub/irs-trty/germany.pdf
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.y2025.bridge_stages import (
    BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
    bridge_law_stages_2025,
)
from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import (
    LawRule,
    LegalInvariantViolation,
    RuleGraphExecution,
    execute_rule_graph,
)
from tax_pipeline.y2025.germany_law import q2
from tax_pipeline.pipeline_context import set_pipeline_context_value


BRIDGE_EXECUTION_CONTEXT_KEY = "bridge25.rule_graph_execution"
"""Pipeline-context key under which ``execute_bridge_rule_graph`` stashes
the executed ``RuleGraphExecution`` for in-memory hand-off (mirrors the
per-jurisdiction context keys used by Germany / U.S. / treaty graphs).
"""

RECONCILED_STATUS = "reconciled"


def bridge25_foreign_tax_reconciliation(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Assert foreign-tax components reconcile to ``capital.explicit_foreign_tax_total``.

    Legal authority and ordering:

    - § 32d Abs. 5 EStG fixes the per-Posten German foreign-tax credit;
      the basis must reconcile to its underlying components before the
      cap is applied. https://www.gesetze-im-internet.de/estg/__32d.html
    - 26 U.S.C. § 901 fixes the IRS foreign-tax credit on the same
      foreign-tax-paid basis.
      https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
    - DBA-USA Art. 23 ties the U.S. and German credit chains so the same
      foreign-tax euros must reconcile across both jurisdictions.

    The reconciliation sums the four independently sourced foreign-tax
    components (1099 / treaty input, German bank-certificate credited
    bucket, German bank-certificate not-yet-credited bucket, treaty
    re-sourcing add-on) and compares against
    ``capital.explicit_foreign_tax_total``. Discrepancy fails closed via
    ``LegalInvariantViolation`` per CLAUDE.md.
    """
    foreign_tax_1099 = q2(
        Decimal(str(facts["bridge.foreign_tax_1099_eur"]))
    )
    bank_credited = q2(
        Decimal(
            str(facts["bridge.bank_certificate_foreign_tax_credited_eur"])
        )
    )
    bank_not_credited = q2(
        Decimal(
            str(
                facts["bridge.bank_certificate_foreign_tax_not_credited_eur"]
            )
        )
    )
    treaty_us_source = q2(
        Decimal(
            str(
                facts[
                    "bridge.treaty_us_source_dividend_allowed_us_tax_eur"
                ]
            )
        )
    )
    capital_total = q2(
        Decimal(
            str(facts["bridge.capital_explicit_foreign_tax_total_eur"])
        )
    )

    reconciliation_total = q2(
        foreign_tax_1099
        + bank_credited
        + bank_not_credited
        + treaty_us_source
    )
    if reconciliation_total != capital_total:
        # Fail closed per § 32d Abs. 5 EStG audit-trail rigor and 26
        # U.S.C. § 901 credit-basis verifiability. The four inputs that
        # feed the reconciliation are independently sourced (CSV 1099
        # rows, German bank certificates, treaty re-sourcing items); a
        # mismatch means the § 32d(5) per-item cap denominator has
        # drifted from its underlying basis and the credit would
        # silently miscount.
        raise LegalInvariantViolation(
            BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
            (
                "foreign_tax components do not reconcile to "
                "capital.explicit_foreign_tax_total: "
                f"foreign_tax_1099_eur={foreign_tax_1099} "
                f"+ bank_certificate_foreign_tax_credited_eur={bank_credited} "
                f"+ bank_certificate_foreign_tax_not_credited_eur={bank_not_credited} "
                f"+ treaty_us_source_dividend_allowed_us_tax_eur={treaty_us_source} "
                f"= reconciliation_total={reconciliation_total} EUR; "
                f"expected capital.explicit_foreign_tax_total={capital_total} EUR. "
                "Update normalized/derived-facts/germany/income-cashflows.csv "
                "foreign_tax rows and bank-certificate inputs so the four "
                "components sum to the per-Posten foreign-tax basis under "
                "§ 32d Abs. 5 EStG and 26 U.S.C. § 901."
            ),
        )

    return {
        "bridge.foreign_tax_reconciliation_total_eur": reconciliation_total,
        "bridge.foreign_tax_reconciliation_status": RECONCILED_STATUS,
    }


_RULE_FUNCTIONS = {
    BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID: bridge25_foreign_tax_reconciliation,
}


def bridge_law_rules_2025() -> tuple[LawRule, ...]:
    stages = bridge_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(
                f"No bridge calculate function registered for {stage.stage_id}"
            )
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def bridge_initial_facts_2025(
    *,
    foreign_tax_1099_eur: Decimal,
    bank_certificate_foreign_tax_credited_eur: Decimal,
    bank_certificate_foreign_tax_not_credited_eur: Decimal,
    treaty_us_source_dividend_allowed_us_tax_eur: Decimal,
    capital_explicit_foreign_tax_total_eur: Decimal,
) -> dict[str, Any]:
    """Assemble the initial-fact dict for ``execute_bridge_rule_graph``.

    The five inputs are the four foreign-tax components plus the
    capital-rule's reconciled basis. Each value should be a per-stage
    q2-quantized EUR amount; the reconciliation rule re-quantizes to
    match the LawStage rounding policy.
    """
    return {
        "bridge.foreign_tax_1099_eur": foreign_tax_1099_eur,
        "bridge.bank_certificate_foreign_tax_credited_eur": (
            bank_certificate_foreign_tax_credited_eur
        ),
        "bridge.bank_certificate_foreign_tax_not_credited_eur": (
            bank_certificate_foreign_tax_not_credited_eur
        ),
        "bridge.treaty_us_source_dividend_allowed_us_tax_eur": (
            treaty_us_source_dividend_allowed_us_tax_eur
        ),
        "bridge.capital_explicit_foreign_tax_total_eur": (
            capital_explicit_foreign_tax_total_eur
        ),
    }


def bridge_initial_fingerprints_2025(
    initial_facts: Mapping[str, Any],
) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_bridge_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        bridge_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(BRIDGE_EXECUTION_CONTEXT_KEY, execution)
    return execution


__all__ = [
    "BRIDGE_EXECUTION_CONTEXT_KEY",
    "RECONCILED_STATUS",
    "bridge25_foreign_tax_reconciliation",
    "bridge_initial_facts_2025",
    "bridge_initial_fingerprints_2025",
    "bridge_law_rules_2025",
    "execute_bridge_rule_graph",
]
