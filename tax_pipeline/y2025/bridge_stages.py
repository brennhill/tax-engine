"""Cross-jurisdiction (BRIDGE-2025) LawStages.

Bridge stages assert legal invariants whose inputs come from more than one
jurisdictional rule graph (Germany capital, U.S. assessment, treaty
re-sourcing). They are first-class members of the rule graph: each
``StageResult`` carries the same fingerprint provenance the per-jurisdiction
stages do, so an audit reviewer can trace the reconciliation total back to
its underlying inputs without leaving the rule-graph surface.

The first bridge stage (``BRIDGE25-FOREIGN-TAX-RECONCILIATION``) replaces
the script-level reconciliation block that lived at
``tax_pipeline/pipelines/y2025/germany_model.py:259-269`` (flagged by
invariants I2 and I5 in ``docs/invariant-migration-plan.md``). The legal
content of the assertion is unchanged — only its location moves into the
audit graph.

Authority for the foreign-tax reconciliation invariant:

- § 32d Abs. 5 EStG (per-Posten foreign-tax credit) requires the
  foreign-tax basis to reconcile to the per-item totals that feed the
  § 32d(5) cap. Without reconciliation the cap denominator drifts.
  https://www.gesetze-im-internet.de/estg/__32d.html
- 26 U.S.C. § 901 (foreign tax credit) requires a verifiable foreign-tax
  amount as the credit basis on Form 1116.
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
- DBA-USA Art. 23 (elimination of double taxation; residence-state
  credit) ties the U.S. and German foreign-tax-credit chains so the same
  euro of foreign tax must reconcile across both jurisdictions.
  https://www.irs.gov/pub/irs-trty/germany.pdf
"""

from __future__ import annotations

from tax_pipeline.core.stages import (
    AuditWaypoint,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.y2025.germany_law import ESTG_32D_URL
from tax_pipeline.y2025.treaty_law import DBA_USA_ART_23_URL
from tax_pipeline.y2025.us_law import USC_901_URL


BRIDGE_2025_SCOPE = "BRIDGE-2025"

BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID = "BRIDGE25-FOREIGN-TAX-RECONCILIATION"


def bridge_law_stages_2025() -> tuple[LawStage, ...]:
    """Cross-jurisdiction reconciliation stages for the 2025 engine."""
    return (
        # BRIDGE25-FOREIGN-TAX-RECONCILIATION: assert that the four
        # independently sourced foreign-tax-paid components (1099 / treaty
        # input, German bank certificate credited bucket, German bank
        # certificate not-yet-credited bucket, treaty re-sourcing add-on)
        # sum to ``capital.explicit_foreign_tax_total``. The check sits
        # between Germany capital assessment (which produces the four
        # components) and the § 32d Abs. 5 per-item cap consumers; failure
        # to reconcile means the cap denominator has drifted from its
        # underlying basis, which would silently miscredit foreign tax
        # under both § 32d EStG and 26 U.S.C. § 901. Per CLAUDE.md the
        # rule fails closed via ``LegalInvariantViolation`` rather than
        # papering over the discrepancy.
        LawStage(
            stage_id=BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
            country_or_scope=BRIDGE_2025_SCOPE,
            legal_refs=(
                "§ 32d Abs. 5 EStG",
                "26 U.S.C. § 901",
                "DBA-USA Art. 23",
            ),
            authority_urls=(ESTG_32D_URL, USC_901_URL, DBA_USA_ART_23_URL),
            input_fact_keys=(
                "bridge.foreign_tax_1099_eur",
                "bridge.bank_certificate_foreign_tax_credited_eur",
                "bridge.bank_certificate_foreign_tax_not_credited_eur",
                "bridge.treaty_us_source_dividend_allowed_us_tax_eur",
                "bridge.capital_explicit_foreign_tax_total_eur",
            ),
            rounding_policy=(
                "Each component is q2-quantized at the producing stage "
                "(EUR cents); the reconciliation comparison uses the same "
                "q2 quantization on both sides of the equality."
            ),
            law_order_note=(
                "The foreign-tax basis must reconcile across the 1099, "
                "German bank-certificate, and treaty re-sourcing inputs "
                "before § 32d Abs. 5 EStG and 26 U.S.C. § 901 can apply "
                "their per-item caps. Reconciliation precedes credit "
                "application."
            ),
            legal_formula=(
                "bridge.foreign_tax_reconciliation_total_eur = "
                "foreign_tax_1099_eur "
                "+ bank_certificate_foreign_tax_credited_eur "
                "+ bank_certificate_foreign_tax_not_credited_eur "
                "+ treaty_us_source_dividend_allowed_us_tax_eur; "
                "assert q2(reconciliation_total) == "
                "q2(capital.explicit_foreign_tax_total)"
            ),
            narrative_templates={
                "en": BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID,
            },
            outputs=(
                OutputDeclaration(
                    key="bridge.foreign_tax_reconciliation_total_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.RECONCILIATION_INVARIANT}
                    ),
                ),
                OutputDeclaration(
                    key="bridge.foreign_tax_reconciliation_status",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.RECONCILIATION_INVARIANT}
                    ),
                ),
            ),
        ),
    )


__all__ = [
    "BRIDGE_2025_SCOPE",
    "BRIDGE25_FOREIGN_TAX_RECONCILIATION_STAGE_ID",
    "bridge_law_stages_2025",
]
