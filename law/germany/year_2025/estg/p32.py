"""
---
jurisdiction: DE
tax_year: 2025
statute: § 32 EStG (Kinder, Kinderfreibetrag, BEA-Freibetrag)
url: https://www.gesetze-im-internet.de/estg/__32.html
contains:
  - § 32 Abs. 6 Satz 1 EStG: Kinderfreibetrag €3,336 / Elternteil
  - § 32 Abs. 6 Satz 1 EStG: BEA-Freibetrag €1,464 / Elternteil
  - § 32 Abs. 6 Satz 3 EStG: full transfer to one parent / single parent
  - § 32 Abs. 6 Satz 4-6 EStG: Übertragung des Freibetrags
  - children-aggregator helper consumed by Pipeline 1 → DERIVE-DE25-CHILDREN
numeric_constants:
  - KINDERFREIBETRAG_2025_EUR: 6672                 # combined per child
  - BEA_FREIBETRAG_2025_EUR: 2928                   # combined per child
  - COMBINED_KINDERFREIBETRAG_2025_EUR: 9600        # sum per child
  - KINDERFREIBETRAG_PER_PARENT_2025_EUR: 3336      # § 32 Abs. 6 Satz 1
  - BEA_FREIBETRAG_PER_PARENT_2025_EUR: 1464        # § 32 Abs. 6 Satz 1
amended_by:
  - Steuerfortentwicklungsgesetz 2024, BGBl. 2024 I (Kinderfreibetrag €3,336)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:13fe4f6c800ffd3fdcd23c61f4d042241f9bf685846d1a2c5249ef677fe0f3be
---
"""
# Shadow extraction of § 32 EStG (Phase 3 composing §). Imports
# § 33b Abs. 5 EStG transferral helper from p33b for the children
# aggregator, and the BKGG Kindergeld helper from bkgg/p6 (forward
# import via tax_pipeline shim because BKGG p6 not yet extracted in this
# scope).
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

# Cross-§ imports for the children aggregator. § 33b Abs. 5 transferral
# helper is local to p33b.py; the BKGG Kindergeld helper still routes
# through the production module (BKGG/p6 is a separate Phase 2 leaf
# extraction, out of scope here).
from law.germany.year_2025.estg.p33b import (
    child_disability_pauschbetrag_for_transferral_2025,
)
from tax_pipeline.y2025.germany_law import (
    KINDERGELD_2025_MONTHLY_EUR,
    KINDERGELD_2025_RECIPIENT_VALUES,
    KINDERGELD_2025_THIS_FILER_RECIPIENTS,
    GermanyChildrenFacts2025,
    kindergeld_for_child_2025,
)

D = Decimal

# § 32 Abs. 6 EStG — Kinderfreibetrag (€6,672 total per child) plus
# BEA-Freibetrag (€2,928 total per child) for the assessment year 2025.
# Each parent claims half by default (€3,336 + €1,464 = €4,800 per
# spouse in married_separate); single parents and married_joint claim
# the full €9,600 combined deduction.
# Authority:
# - § 32 Abs. 6 Satz 1 EStG (Kinderfreibetrag €3,336 / Elternteil),
# - § 32 Abs. 6 Satz 2 EStG (BEA €1,464 / Elternteil),
# - § 32 Abs. 6 Satz 3 EStG (full transfer to one parent / single parent).
# Effective from BGBl. I 2024 (Steuerfortentwicklungsgesetz).
# https://www.gesetze-im-internet.de/estg/__32.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
KINDERFREIBETRAG_2025_EUR = _CONSTANTS["KINDERFREIBETRAG_2025_EUR"]
BEA_FREIBETRAG_2025_EUR = _CONSTANTS["BEA_FREIBETRAG_2025_EUR"]
COMBINED_KINDERFREIBETRAG_2025_EUR = _CONSTANTS["COMBINED_KINDERFREIBETRAG_2025_EUR"]

# Per-parent half-amounts under § 32 Abs. 6 Satz 1 EStG. Surfaced as
# named constants so callers can reason about married-separate per-spouse
# deductions explicitly.
KINDERFREIBETRAG_PER_PARENT_2025_EUR = _CONSTANTS["KINDERFREIBETRAG_PER_PARENT_2025_EUR"]
BEA_FREIBETRAG_PER_PARENT_2025_EUR = _CONSTANTS["BEA_FREIBETRAG_PER_PARENT_2025_EUR"]


def kinderfreibetrag_for_child_2025(
    months_in_household: int,
    *,
    filing_posture: str,
) -> Decimal:
    """§ 32 Abs. 6 EStG per-child Kinderfreibetrag + BEA-Freibetrag.

    Returns the deduction available against zvE for one qualifying child
    given the months the child was in the household. Partial-year
    proration is by full months. MFS halves the per-child amount because
    the Freibetrag is split between parents.

    Authority: § 32 Abs. 6 Sätze 1-3 EStG.
    https://www.gesetze-im-internet.de/estg/__32.html
    """
    if months_in_household < 0 or months_in_household > 12:
        raise ValueError(
            "months_in_household must be in [0, 12] under § 32 Abs. 6 EStG."
        )
    if filing_posture not in {"single", "married_joint", "married_separate"}:
        raise ValueError(
            f"Unsupported Germany filing posture for Kinderfreibetrag: {filing_posture}"
        )
    full_amount = COMBINED_KINDERFREIBETRAG_2025_EUR
    if filing_posture == "married_separate":
        # § 32 Abs. 6 Satz 1/2 EStG halves to €4,800 per spouse when
        # parents are jointly entitled but file separately.
        full_amount = full_amount / D("2")
    proration = D(months_in_household) / D("12")
    return q2(full_amount * proration)


def kinderfreibetrag_per_child_2025_eur(
    *,
    filing_posture: str,
) -> Decimal:
    """§ 32 Abs. 6 EStG per-child full-year amount under the given posture.

    Returns the un-prorated annual deduction:
    - single / married_joint: €9,600
    - married_separate: €4,800

    Authority: § 32 Abs. 6 Sätze 1-3 EStG.
    """
    if filing_posture not in {"single", "married_joint", "married_separate"}:
        raise ValueError(
            f"Unsupported Germany filing posture for Kinderfreibetrag: {filing_posture}"
        )
    if filing_posture == "married_separate":
        return COMBINED_KINDERFREIBETRAG_2025_EUR / D("2")
    return COMBINED_KINDERFREIBETRAG_2025_EUR


def aggregate_germany_children_facts_2025(
    children: tuple[object, ...],
    *,
    filing_posture: str,
    disability_pauschbetrag_transfer_election: bool = False,
) -> GermanyChildrenFacts2025:
    """Sum per-child Kinderfreibetrag + Kindergeld for the household.

    Filters out non-qualifying children (relationship other than
    qualifying_child); qualifying_relative rows are tracked on the U.S.
    side via the same Child2025 schema but never count toward the German
    Kinderfreibetrag.

    Authority: § 31 EStG / § 32 Abs. 6 EStG / BKGG / § 33b Abs. 3 EStG /
    § 33b Abs. 5 EStG.
    https://www.gesetze-im-internet.de/estg/__31.html
    https://www.gesetze-im-internet.de/estg/__32.html
    https://www.gesetze-im-internet.de/estg/__33b.html
    https://www.gesetze-im-internet.de/bkgg_1996/
    """
    if filing_posture not in {"single", "married_joint", "married_separate"}:
        raise ValueError(
            f"Unsupported Germany filing posture for children aggregation: {filing_posture}"
        )
    qualifying = tuple(c for c in children if c.relationship == "qualifying_child")
    children_count = len(qualifying)
    kinderfreibetrag_total = D("0.00")
    kindergeld_total = D("0.00")
    disability_transferred_total = D("0.00")
    for child in qualifying:
        kinderfreibetrag_total += kinderfreibetrag_for_child_2025(
            int(child.months_in_household),
            filing_posture=filing_posture,
        )
        kindergeld_total += kindergeld_for_child_2025(
            int(child.months_in_household),
            child.kindergeld_recipient,
        )
        # § 33b Abs. 5 EStG transferral — only summed when the election
        # is active.
        disability_transferred_total += child_disability_pauschbetrag_for_transferral_2025(
            child=child,
            transfer_election_active=disability_pauschbetrag_transfer_election,
        )
    return GermanyChildrenFacts2025(
        children=tuple(children),
        children_present=children_count > 0,
        children_count=children_count,
        kinderfreibetrag_total_eur=q2(kinderfreibetrag_total),
        kindergeld_received_total_eur=q2(kindergeld_total),
        disability_pauschbetrag_total_transferred_eur=q2(
            disability_transferred_total
        ),
    )


__all__ = (
    "KINDERFREIBETRAG_2025_EUR",
    "BEA_FREIBETRAG_2025_EUR",
    "COMBINED_KINDERFREIBETRAG_2025_EUR",
    "KINDERFREIBETRAG_PER_PARENT_2025_EUR",
    "BEA_FREIBETRAG_PER_PARENT_2025_EUR",
    "kinderfreibetrag_for_child_2025",
    "kinderfreibetrag_per_child_2025_eur",
    "aggregate_germany_children_facts_2025",
)
