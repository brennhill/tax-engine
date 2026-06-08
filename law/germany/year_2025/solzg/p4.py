"""
---
jurisdiction: DE
tax_year: 2025
statute: § 4 SolzG 1995 (Zuschlagssatz, Freigrenze, Milderungszone)
url: https://www.gesetze-im-internet.de/solzg_1995/__4.html
contains:
  - § 4 Satz 1 SolzG 1995: 5,5 % rate (the rate constant lives in solzg/p3.py
    so the "assessment base" file owns the canonical SOLI_RATE; § 4 owns the
    Freigrenze + Milderungszone)
  - § 3 Abs. 3 SolzG 1995: Soli-Freigrenze (single €19.950, joint €39.900);
    posture-specific upper bound below which the surcharge is zero
  - § 4 Satz 2 SolzG 1995: Milderungszone (mitigation rate 11,9 %) capping
    the surcharge above the Freigrenze
numeric_constants:
  - SOLI_SINGLE_THRESHOLD_EUR: 19950.00  # § 3 Abs. 3 SolzG 1995 (single posture)
  - SOLI_JOINT_THRESHOLD_EUR: 39900.00   # § 3 Abs. 3 SolzG 1995 (joint posture)
  - SOLI_MITIGATION_RATE: 0.119          # § 4 Satz 2 SolzG 1995
amended_by:
  - Gesetz zur Rückführung des Solidaritätszuschlags 1995 (BGBl. I 2019 S. 2115)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:30114f4807630121878f35d45e20a9a9357f6ff8ab58bb4101446e58a348bbe7
---
"""
# Shadow extraction of § 4 SolzG 1995 (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte. Imports the canonical
# SOLI_RATE from the paired solzg/p3 file so the rate has a single edit
# point per invariant I1.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import floor_cent
from law.germany.year_2025.solzg.p3 import SOLI_RATE

D = Decimal

# § 3 Abs. 3 SolzG 1995: Soli-Freigrenze (the festgesetzte Einkommensteuer
# below which no Solidaritätszuschlag is assessed). Posture-specific:
# single/getrennte Veranlagung uses €19.950; Splittingverfahren uses
# €39.900 (twice the single Freigrenze).
# https://www.gesetze-im-internet.de/solzg_1995/__4.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SOLI_SINGLE_THRESHOLD_EUR = _CONSTANTS["SOLI_SINGLE_THRESHOLD_EUR"]
SOLI_JOINT_THRESHOLD_EUR = _CONSTANTS["SOLI_JOINT_THRESHOLD_EUR"]
# § 4 Satz 2 SolzG 1995: Milderungszone — between the Freigrenze and the
# point where the full 5,5 % rate would apply, the surcharge is capped at
# 11,9 % of the excess of the assessment base over the Freigrenze.
# https://www.gesetze-im-internet.de/solzg_1995/__4.html
SOLI_MITIGATION_RATE = _CONSTANTS["SOLI_MITIGATION_RATE"]


def german_soli_assessment_2025(
    ordinary_income_tax_eur: Decimal,
    *,
    filing_posture: str = "married_joint",
) -> Decimal:
    """§ 3 + § 4 SolzG 1995 Solidaritätszuschlag assessment.

    Authority: § 3 Abs. 3 SolzG 1995 (Freigrenze) + § 4 SolzG 1995 (5,5 %
    rate, 11,9 % Milderungszone cap).
    - https://www.gesetze-im-internet.de/solzg_1995/__3.html
    - https://www.gesetze-im-internet.de/solzg_1995/__4.html
    """
    # 2025 solidarity-surcharge free limits from SolzG § 3 and § 4 are posture-specific:
    # single/separate assessments use 19,950 EUR; splitting assessments use 39,900 EUR.
    posture = filing_posture.strip().lower()
    if posture in {"single", "married_separate"}:
        threshold = SOLI_SINGLE_THRESHOLD_EUR
    elif posture == "married_joint":
        threshold = SOLI_JOINT_THRESHOLD_EUR
    else:
        raise ValueError(f"Unsupported Germany solidarity-surcharge filing posture: {filing_posture}")
    if ordinary_income_tax_eur <= threshold:
        return D("0.00")
    raw = floor_cent(ordinary_income_tax_eur * SOLI_RATE)
    mitigation = floor_cent((ordinary_income_tax_eur - threshold) * SOLI_MITIGATION_RATE)
    return min(raw, mitigation)
