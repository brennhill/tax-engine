"""
---
jurisdiction: DE
tax_year: 2025
statute: § 10b EStG (Spendenabzug)
url: https://www.gesetze-im-internet.de/estg/__10b.html
contains:
  - § 10b Abs. 1 Satz 1 Nr. 1 EStG: 20% of GdE cap on charitable donations
  - § 10b Abs. 1 Sätze 9-10 EStG: Großspendenrest carryforward (NOT modeled — fail closed)
numeric_constants:
  - SPENDENABZUG_2025_GDE_FRACTION_CAP: 0.20
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:5b77904da6e650ee3824d161253b13031504375e9816f57bcc1432c005f24dc2
---
"""
# Shadow extraction of § 10b EStG (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# § 10b Abs. 1 Satz 1 Nr. 1 EStG: deductible Sonderausgabe = min(donations,
# 20% of Gesamtbetrag der Einkünfte). The 4‰ "Umsatz + Lohnsumme"
# entrepreneur cap (§ 10b Abs. 1 Satz 1 Nr. 2 EStG) is out of scope.
# https://www.gesetze-im-internet.de/estg/__10b.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SPENDENABZUG_2025_GDE_FRACTION_CAP = _CONSTANTS["SPENDENABZUG_2025_GDE_FRACTION_CAP"]


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def spendenabzug_2025(
    *,
    donations_eur: Decimal,
    gesamtbetrag_der_einkuenfte_eur: Decimal,
    carryforward_eur: Decimal,
) -> Decimal:
    """§ 10b Abs. 1 Satz 1 Nr. 1 EStG: charitable Sonderausgabe.

    Cap = 20 % of GdE. § 10b Abs. 1 Sätze 9-10 EStG carryforwards
    (Großspendenrest) are NOT modeled — the function fails closed if any
    carryforward is asserted (per CLAUDE.md fail-closed posture).

    Authority: § 10b Abs. 1 Satz 1 Nr. 1 EStG.
    https://www.gesetze-im-internet.de/estg/__10b.html
    """
    # § 10b Abs. 1 Satz 1 Nr. 1 EStG: deductible Sonderausgabe = min(
    # donations, 20 % of GdE). § 10b Abs. 1 Sätze 9-10 EStG carryforwards
    # are not modeled — fail closed if any carryforward is asserted.
    _require_non_negative_decimal(donations_eur, label="donations_eur")
    _require_non_negative_decimal(
        gesamtbetrag_der_einkuenfte_eur, label="gesamtbetrag_der_einkuenfte_eur"
    )
    _require_non_negative_decimal(carryforward_eur, label="carryforward_eur")
    if carryforward_eur > D("0.00"):
        raise NotImplementedError(
            "§ 10b Abs. 1 Sätze 9-10 EStG donation carryforwards "
            "(Großspendenrest) are not modeled for 2025; the workspace "
            "asserts a non-zero charitable_donations_carryforward_eur. "
            "Resolve manually before running the pipeline."
        )
    cap = q2(gesamtbetrag_der_einkuenfte_eur * SPENDENABZUG_2025_GDE_FRACTION_CAP)
    return q2(min(donations_eur, cap))
