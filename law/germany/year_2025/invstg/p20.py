"""
---
jurisdiction: DE
tax_year: 2025
statute: § 20 InvStG 2018 (Teilfreistellung)
url: https://www.gesetze-im-internet.de/invstg_2018/__20.html
contains:
  - § 20 Abs. 1 Nr. 1 InvStG: Aktienfonds (≥ 51 % Kapitalbeteiligungen) → 30 % Teilfreistellung
  - § 20 Abs. 1 Nr. 2 InvStG: Mischfonds (≥ 25 % Kapitalbeteiligungen) → 15 % Teilfreistellung
  - § 20 Abs. 3 Nr. 1 InvStG: Immobilienfonds (inländisch) → 60 % Teilfreistellung
  - § 20 Abs. 3 Nr. 2 InvStG: ausländische Immobilienfonds → 80 % Teilfreistellung
  - § 20 InvStG (Auffangkategorie): sonstige Investmentfonds → 0 % Teilfreistellung
  - normalized_fund_type_2025: validated lookup of a normalized fund-type label
  - fund_type_for_symbol_2025: per-symbol fund-type lookup with fail-closed missing-classification
numeric_constants:
  - FUND_TEILFREISTELLUNG_RATES_2025 (table):
      aktienfonds / equity:                  0.30  # § 20 Abs. 1 Nr. 1 InvStG
      mischfonds / mixed:                    0.15  # § 20 Abs. 1 Nr. 2 InvStG
      immobilienfonds / property:            0.60  # § 20 Abs. 3 Nr. 1 InvStG
      auslands_immobilienfonds / foreign_property: 0.80  # § 20 Abs. 3 Nr. 2 InvStG
      sonstige / other:                      0.00  # Auffangkategorie
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:a2606e628dbcec05ab26d866c46d1578fb895f3266de5386c560e7ed675ce4b6
---
"""
# Shadow extraction of § 20 InvStG 2018 (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte. The fund-type lookup
# helpers fail closed when a symbol is missing from the workspace
# classification mapping (no silent default to Aktienfonds / 30 %).
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_tables

D = Decimal

# § 20 InvStG 2018 Teilfreistellung rates by fund type. The English
# aliases (equity / mixed / property / foreign_property / other) are
# accepted alongside the German labels to ease workspace authoring.
# Authority: § 20 Abs. 1 Nr. 1, Abs. 1 Nr. 2, Abs. 3 Nr. 1, Abs. 3 Nr. 2
# InvStG 2018.
# https://www.gesetze-im-internet.de/invstg_2018/__20.html
# Statutory schedule lives in the sibling .toml data file (W2.A / T1.2,
# see .review/2026-05-11-implementation-plan.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_TABLES = load_tables(Path(__file__).with_suffix(".toml"))
# Convert the frozen MappingProxyType view to a plain ``dict`` so the
# downstream production module's table (declared as a regular dict) and
# this shadow's table compare equal under ``==``.
FUND_TEILFREISTELLUNG_RATES_2025: dict[str, Decimal] = dict(
    _TABLES["FUND_TEILFREISTELLUNG_RATES_2025"]
)


def normalized_fund_type_2025(raw: object, *, symbol: str) -> str:
    """Validate and normalize a fund-type label against the § 20 InvStG schedule.

    Authority: § 20 InvStG 2018.
    https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """
    fund_type = str(raw).strip().lower()
    if fund_type not in FUND_TEILFREISTELLUNG_RATES_2025:
        raise ValueError(
            f"Fund classification for {symbol} must be one of: "
            + ", ".join(sorted(FUND_TEILFREISTELLUNG_RATES_2025))
        )
    return fund_type


def fund_type_for_symbol_2025(symbol: str, fund_classification: dict[str, str]) -> str:
    """Per-symbol fund-type lookup; fail-closed when classification missing.

    Authority: § 20 InvStG 2018 Teilfreistellung.
    https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """
    cleaned = symbol.strip().upper()
    if cleaned not in fund_classification:
        # InvStG § 20 has materially different Teilfreistellung rates by fund type.
        # Missing classification must fail closed instead of defaulting to Aktienfonds.
        raise ValueError(f"Fund classification missing for fund_like symbol {cleaned}.")
    return normalized_fund_type_2025(fund_classification[cleaned], symbol=cleaned)
