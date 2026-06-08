"""
---
jurisdiction: DE
tax_year: 2025
statute: § 32a EStG (Einkommensteuertarif)
url: https://www.gesetze-im-internet.de/estg/__32a.html
contains:
  - § 32a Abs. 1 EStG: Grundtarif (Grundfreibetrag, Progressionszonen, Spitzensteuersatz)
  - § 32a Abs. 1 Nr. 5 EStG: Reichensteuer 45 % ab €277.826
  - § 32a Abs. 5 EStG: Splittingtarif (combined with § 26b EStG)
numeric_constants:
  - TARIFF_2025_GROUND_ALLOWANCE_EUR: 12096
  - TARIFF_2025_PROGRESS_ZONE_1_END_EUR: 17443
  - TARIFF_2025_PROGRESS_ZONE_2_END_EUR: 68480
  - TARIFF_2025_TOP_RATE_START_EUR: 277825
amended_by:
  - Steuerfortentwicklungsgesetz 2024, BGBl. 2024 I (2025 Grundfreibetrag €12,096)
  - BMF Programmablaufplan 2025 (official tariff coefficients)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:e6fcc0f7d4af39da7139dd1e0318caf29a4dd0e7be0b412b2a0ece3ede83e02f
---
"""
# Shadow extraction of § 32a EStG Tariff (Phase 3 composing §). Does not
# depend on any other §. Mirrors ``tax_pipeline.y2025.germany_law``
# byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import floor_euro

D = Decimal

# Official 2025 tariff constants from the dated BMF Programmablaufplan
# 2025 and § 32a Abs. 1 EStG. Live statute URL can roll forward to
# later-year constants.
# https://www.gesetze-im-internet.de/estg/__32a.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
TARIFF_2025_GROUND_ALLOWANCE_EUR = _CONSTANTS["TARIFF_2025_GROUND_ALLOWANCE_EUR"]
TARIFF_2025_PROGRESS_ZONE_1_END_EUR = _CONSTANTS["TARIFF_2025_PROGRESS_ZONE_1_END_EUR"]
TARIFF_2025_PROGRESS_ZONE_2_END_EUR = _CONSTANTS["TARIFF_2025_PROGRESS_ZONE_2_END_EUR"]
# § 32a Abs. 1 Nr. 5 EStG: the 45 % Reichensteuer applies "ab €277.826".
# This constant is the inclusive UPPER BOUND of the 42 % zone (one euro
# below the start of the 45 % zone) — the rule body uses ``x <=
# TARIFF_2025_TOP_RATE_START_EUR`` so the comparison stays correct, but
# the name is a legacy artifact: the value is *not* the first euro of
# the 45 % bracket.
# https://www.gesetze-im-internet.de/estg/__32a.html
TARIFF_2025_TOP_RATE_START_EUR = _CONSTANTS["TARIFF_2025_TOP_RATE_START_EUR"]


def german_income_tax_single_2025(zve_eur: Decimal) -> Decimal:
    """§ 32a Abs. 1 EStG Grundtarif (single-filer income tax).

    Authority: § 32a Abs. 1 EStG; coefficients from the official 2025
    BMF Programmablaufplan.
    https://www.gesetze-im-internet.de/estg/__32a.html
    """
    # Official tariff formula and rounding order from § 32a Abs. 1 EStG.
    x = floor_euro(zve_eur)
    if x <= TARIFF_2025_GROUND_ALLOWANCE_EUR:
        tax = D("0")
    elif x <= TARIFF_2025_PROGRESS_ZONE_1_END_EUR:
        y = (x - TARIFF_2025_GROUND_ALLOWANCE_EUR) / D("10000")
        tax = (D("932.30") * y + D("1400")) * y
    elif x <= TARIFF_2025_PROGRESS_ZONE_2_END_EUR:
        z = (x - TARIFF_2025_PROGRESS_ZONE_1_END_EUR) / D("10000")
        tax = (D("176.64") * z + D("2397")) * z + D("1015.13")
    elif x <= TARIFF_2025_TOP_RATE_START_EUR:
        tax = D("0.42") * x - D("10911.92")
    else:
        tax = D("0.45") * x - D("19246.67")
    return floor_euro(tax)


def german_income_tax_split_2025(zve_eur: Decimal) -> Decimal:
    """§ 32a Abs. 5 EStG Splittingtarif (combined with § 26b EStG).

    Authority: § 26b EStG (joint assessment) + § 32a Abs. 5 EStG
    (Splittingverfahren).
    """
    # Joint splitting under § 26b and § 32a Abs. 5 EStG.
    return floor_euro(german_income_tax_single_2025(zve_eur / D("2")) * D("2"))
