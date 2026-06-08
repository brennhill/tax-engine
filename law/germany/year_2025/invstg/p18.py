"""
---
jurisdiction: DE
tax_year: 2025
statute: § 18 InvStG 2018 (Vorabpauschale)
url: https://www.gesetze-im-internet.de/invstg_2018/__18.html
contains:
  - § 18 Abs. 1 Satz 1 InvStG: Basisertrag = NAV_start × 0,7 × Basiszinssatz
    (annual proration via § 18 Abs. 2: 1/12 per month not held the full year)
  - § 18 Abs. 1 Satz 3 InvStG: Basisertrag is reduced by year's Ausschuettungen
    before becoming the Vorabpauschale
  - 2025 Basiszinssatz published by BMF on 16.01.2025 (IV C 1 - S 1980-1/19/10005:008)
numeric_constants:
  - VORABPAUSCHALE_BASISERTRAG_FACTOR: 0.7   # § 18 Abs. 1 Satz 1 InvStG
  - BASISZINS_2025: 0.0253                    # BMF 16.01.2025 (Az. IV C 1 - S 1980-1/19/10005:008)
amended_by:
  - BMF-Schreiben 16.01.2025 (Basiszinssatz 2,53 % für 2025)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:334faa20c2b9918627e1bee68f53eba8a273528089acd43836e5137f48adbe8f
---
"""
# Shadow extraction of § 18 InvStG 2018 (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte. The Vorabpauschale
# formula itself is composed inside the DE25-13F-VORABPAUSCHALE rule
# body (the cap step lives in § 16 InvStG; the Teilfreistellung step
# lives in § 20 InvStG / invstg/p20.py).
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

D = Decimal

# § 18 Abs. 1 Satz 1 InvStG: Basisertrag = NAV_start × 0,7 × Basiszinssatz
# × (months_held / 12). The 0,7 factor is the statutory shortfall (70 %
# of the risk-free rate) that § 18 InvStG applies to the prior-year NAV.
# https://www.gesetze-im-internet.de/invstg_2018/__18.html
# https://www.gesetze-im-internet.de/invstg_2018/__19.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
VORABPAUSCHALE_BASISERTRAG_FACTOR = _CONSTANTS["VORABPAUSCHALE_BASISERTRAG_FACTOR"]
# BMF-Schreiben 16.01.2025 - IV C 1 - S 1980-1/19/10005:008 — the 2025
# Basiszinssatz (2,53 %) used by InvStG § 18 to compute the
# Vorabpauschale Basisertrag. Source: BMF Investmentfonds page (annual
# Basiszinssatz announcements).
# https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuergesetz/2025-01-16-basiszins-zur-berechnung-der-vorabpauschale.pdf?__blob=publicationFile&v=2
BASISZINS_2025 = _CONSTANTS["BASISZINS_2025"]
