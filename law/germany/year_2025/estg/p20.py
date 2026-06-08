"""
---
jurisdiction: DE
tax_year: 2025
statute: § 20 EStG (Einkünfte aus Kapitalvermögen)
url: https://www.gesetze-im-internet.de/estg/__20.html
contains:
  - § 20 Abs. 9 Satz 1 EStG: Sparer-Pauschbetrag €1,000 single
  - § 20 Abs. 9 Satz 2 EStG: Sparer-Pauschbetrag €2,000 joint
  - § 20 Abs. 9 Satz 3 EStG: per-spouse split + transferable excess
numeric_constants:
  - SAVER_ALLOWANCE_SINGLE_2025_EUR: 1000
  - SAVER_ALLOWANCE_JOINT_2025_EUR: 2000
amended_by:
  - Jahressteuergesetz 2022 (BGBl. I 2022 S. 2294) — €1,000 / €2,000 from 2023
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:82b10df701d9c6dd7933be3fa228913b7c9d11d578241df7cce2525918a89775
---
"""
# Shadow extraction of § 20 EStG Sparer-Pauschbetrag (Phase 3 composing §).
# Mirrors ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# § 20 Abs. 9 Satz 1 EStG: Sparer-Pauschbetrag — €1,000 per single filer,
# €2,000 for jointly assessed spouses (§ 20 Abs. 9 Satz 2 EStG).
# https://www.gesetze-im-internet.de/estg/__20.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SAVER_ALLOWANCE_JOINT_2025_EUR = _CONSTANTS["SAVER_ALLOWANCE_JOINT_2025_EUR"]
SAVER_ALLOWANCE_SINGLE_2025_EUR = _CONSTANTS["SAVER_ALLOWANCE_SINGLE_2025_EUR"]


def saver_allowance_for_spouse_20_9_2025(
    own_capital_before_allowance: Decimal,
    other_spouse_capital_before_allowance: Decimal,
    joint_saver_allowance_eur: Decimal,
) -> Decimal:
    """§ 20 Abs. 9 Satz 3 EStG per-spouse Sparer-Pauschbetrag with transfer.

    Allocates half the joint Sparer-Pauschbetrag to each spouse first;
    only unused excess from one spouse transfers to the other. A negative
    other-spouse bucket cannot create more than the statutory joint
    allowance.

    Authority: § 20 Abs. 9 Satz 3 EStG.
    https://www.gesetze-im-internet.de/estg/__20.html
    """
    # § 20 Abs. 9 Satz 3 EStG allocates half the joint Sparer-Pauschbetrag to each
    # spouse first; only unused excess from one spouse transfers to the other. A
    # negative other-spouse bucket cannot create more than the statutory joint
    # allowance.
    per_spouse_allowance = q2(joint_saver_allowance_eur / D("2"))
    own_positive_capital = max(D("0.00"), own_capital_before_allowance)
    other_positive_capital = max(D("0.00"), other_spouse_capital_before_allowance)
    transferable_excess = max(
        D("0.00"),
        per_spouse_allowance - min(other_positive_capital, per_spouse_allowance),
    )
    return q2(
        min(
            own_positive_capital,
            joint_saver_allowance_eur,
            per_spouse_allowance + transferable_excess,
        )
    )
