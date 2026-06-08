"""
---
jurisdiction: DE
tax_year: 2025
statute: § 33a EStG (Außergewöhnliche Belastungen in besonderen Fällen)
url: https://www.gesetze-im-internet.de/estg/__33a.html
contains:
  - § 33a Abs. 1 Satz 1 EStG: cap at Grundfreibetrag (§ 32a Abs. 1 EStG)
  - § 33a Abs. 1 Satz 5 EStG: recipient's own income above €624 reduces cap
numeric_constants:
  - UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR: 624.00
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:f7c45c61aae353126f4aad73c4f71b44ab7d491f24e5458b02028a41f4f1c034
---
"""
# Shadow extraction of § 33a Abs. 1 EStG (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# § 33a Abs. 1 Satz 1 EStG: maximum deductible Unterhaltsleistungen tracks
# the Grundfreibetrag (= TARIFF_2025_GROUND_ALLOWANCE_EUR for 2025).
# § 33a Abs. 1 Satz 5 EStG: recipient's own income/maintenance above €624
# ("Eigenbezüge und Bezüge") reduces the cap euro for euro.
# https://www.gesetze-im-internet.de/estg/__33a.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR = _CONSTANTS["UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR"]
UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS = frozenset({
    "estranged_spouse",
    "divorced_spouse",
    "parent",
    "child_no_kindergeld",
})


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def unterhaltsleistungen_deductible_2025(
    *,
    support_payments_eur: Decimal,
    recipient_income_eur: Decimal,
    relationship: str,
    grundfreibetrag_eur: Decimal,
) -> Decimal:
    """§ 33a Abs. 1 EStG support-payment deduction.

    Authority: § 33a Abs. 1 Satz 1 EStG (cap at Grundfreibetrag from
    § 32a Abs. 1 EStG); § 33a Abs. 1 Satz 5 EStG (Eigenbezüge €624
    reduction).
    https://www.gesetze-im-internet.de/estg/__33a.html
    """
    # § 33a Abs. 1 Satz 1 EStG: deductible support payments capped at the
    # Grundfreibetrag (§ 32a Abs. 1 EStG). § 33a Abs. 1 Satz 5 EStG reduces
    # the cap by the recipient's own income exceeding €624 ("Eigenbezüge
    # und Bezüge"). Relationship gates eligibility per § 33a Abs. 1 Satz 1
    # EStG (legal duty of support).
    _require_non_negative_decimal(support_payments_eur, label="support_payments_eur")
    _require_non_negative_decimal(recipient_income_eur, label="recipient_income_eur")
    _require_non_negative_decimal(grundfreibetrag_eur, label="grundfreibetrag_eur")
    cleaned_relationship = (relationship or "").strip().lower()
    if support_payments_eur == D("0.00") and not cleaned_relationship:
        return D("0.00")
    if cleaned_relationship not in UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS:
        raise ValueError(
            "Unsupported support_recipient_relationship "
            f"{relationship!r}; expected one of "
            f"{sorted(UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS)} per § 33a Abs. 1 EStG."
        )
    eigenbezuege_reduction = max(
        D("0.00"),
        recipient_income_eur - UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR,
    )
    cap = max(D("0.00"), grundfreibetrag_eur - eigenbezuege_reduction)
    return q2(min(support_payments_eur, cap))
