"""
---
jurisdiction: DE
tax_year: 2025
statute: § 22 Nr. 3 EStG (Sonstige Einkünfte aus Leistungen)
url: https://www.gesetze-im-internet.de/estg/__22.html
contains:
  - § 22 Nr. 3 Satz 2 EStG: €256 Freigrenze on Leistungen
numeric_constants:
  - OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR: 256.00  # § 22 Nr. 3 Satz 2 EStG
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:0a3a0442909ca3097cbd5fdc86f21593b8d62d9fc063995541333cc32d5cceac
---
"""
# Shadow extraction of § 22 Nr. 3 EStG (Phase 2 leaf §; the Phase 1 pilot
# case in MIGRATION.md). Mirrors ``tax_pipeline.y2025.germany_law``
# byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# § 22 Nr. 3 Satz 2 EStG: €256 Freigrenze for sonstige Einkünfte from
# Leistungen, including modeled staking-style receipts. Note this is a
# Freigrenze (cliff), not a Freibetrag (allowance) — once crossed, the
# full amount is taxable.
# https://www.gesetze-im-internet.de/estg/__22.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR = _CONSTANTS["OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR"]


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def other_income_22nr3_taxable_2025(
    other_income_eur: Decimal,
    threshold_eur: Decimal,
) -> Decimal:
    """§ 22 Nr. 3 Satz 2 EStG cliff: full amount taxable once threshold crossed.

    Authority: § 22 Nr. 3 Satz 2 EStG.
    https://www.gesetze-im-internet.de/estg/__22.html
    """
    # § 22 Nr. 3 EStG uses a Freigrenze. Once crossed, the full amount is taxable.
    _require_non_negative_decimal(other_income_eur, label="other_income_eur")
    _require_non_negative_decimal(threshold_eur, label="threshold_eur")
    return q2(other_income_eur if other_income_eur >= threshold_eur else D("0.00"))
