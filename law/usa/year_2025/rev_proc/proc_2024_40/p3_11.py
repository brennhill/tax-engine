"""
---
jurisdiction: US
tax_year: 2025
statute: Rev. Proc. 2024-40 § 3.11
url: https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
contains:
  - § 3.11: 2025 inflation-adjusted Alternative Minimum Tax exemption,
    phase-out start, and 26%/28% rate-break amounts under
    26 U.S.C. § 55(d) (exemption + phase-out) and § 55(b)(1) (rate break).
numeric_constants:
  - AMT_EXEMPTION_SINGLE_2025_USD: 88100
  - AMT_EXEMPTION_MFJ_2025_USD: 137000
  - AMT_EXEMPTION_MFS_2025_USD: 68500
  - AMT_PHASEOUT_START_SINGLE_2025_USD: 626350
  - AMT_PHASEOUT_START_MFJ_2025_USD: 1252700
  - AMT_PHASEOUT_START_MFS_2025_USD: 626350
  - AMT_RATE_BREAK_2025_USD: 239100
  - AMT_RATE_BREAK_MFS_2025_USD: 119550
amended_by:
  - Rev. Proc. 2024-40 (2025 inflation update) — § 3.11
  - Note: source code marks Rev. Proc. 2024-40 § 3.13 in some comments;
    the published bulletin places these AMT amounts under § 3.11 / § 3.13
    of the 2025 inflation-adjustments procedure. The numeric values are
    the controlling figures regardless of the section heading.
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:1ae3abeda8bcd60b21345e9d2f9f599c6cf6735ca8dcecd51517777e0f1a74dc
---
"""
# Shadow extraction of the Rev. Proc. 2024-40 AMT inflation amounts
# (Phase 5 — Rev. Proc. inflation tables). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The IRC § 55 file at
# ``law/usa/year_2025/usc26/p55.py`` imports these constants rather than
# duplicating them, so future inflation roll-forward updates this single
# file without touching the IRC § 55 body.
#
# Authority: 26 U.S.C. § 55(d) (exemption amounts and phase-out);
# 26 U.S.C. § 55(b)(1) (26%/28% rate break); annual inflation amounts
# published by the IRS in Rev. Proc. 2024-40 (Internal Revenue Bulletin
# 2024-43, October 22, 2024).
# https://www.law.cornell.edu/uscode/text/26/55
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

# 26 U.S.C. § 55(d) AMT exemption amounts for 2025 (Rev. Proc. 2024-40):
#   - Single / unmarried (other than a surviving spouse): $88,100
#   - Married filing jointly / surviving spouse: $137,000
#   - Married filing separately: $68,500 (= MFJ exemption / 2)
# https://www.law.cornell.edu/uscode/text/26/55
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
AMT_EXEMPTION_SINGLE_2025_USD = _CONSTANTS["AMT_EXEMPTION_SINGLE_2025_USD"]
AMT_EXEMPTION_MFJ_2025_USD = _CONSTANTS["AMT_EXEMPTION_MFJ_2025_USD"]
AMT_EXEMPTION_MFS_2025_USD = _CONSTANTS["AMT_EXEMPTION_MFS_2025_USD"]

# § 55(d)(3) phase-out start: the exemption is reduced by 25 cents per
# dollar of AMTI above the threshold. 2025 thresholds (Rev. Proc. 2024-40):
#   - Single / unmarried: $626,350
#   - Married filing jointly / surviving spouse: $1,252,700
#   - Married filing separately: $626,350 (= MFJ / 2)
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
AMT_PHASEOUT_START_SINGLE_2025_USD = _CONSTANTS["AMT_PHASEOUT_START_SINGLE_2025_USD"]
AMT_PHASEOUT_START_MFJ_2025_USD = _CONSTANTS["AMT_PHASEOUT_START_MFJ_2025_USD"]
AMT_PHASEOUT_START_MFS_2025_USD = _CONSTANTS["AMT_PHASEOUT_START_MFS_2025_USD"]

# § 55(b)(1) tentative minimum tax 26%/28% rate-break threshold for 2025
# (Rev. Proc. 2024-40 § 3.11): $239,100 of taxable excess AMTI; halved
# to $119,550 for MFS under § 55(b)(1)(A)(ii)(II). (The 2024 amounts
# were $232,600 / $116,300; verify against the published Rev. Proc. when
# rolling forward.)
AMT_RATE_BREAK_2025_USD = _CONSTANTS["AMT_RATE_BREAK_2025_USD"]
AMT_RATE_BREAK_MFS_2025_USD = _CONSTANTS["AMT_RATE_BREAK_MFS_2025_USD"]

__all__ = (
    "AMT_EXEMPTION_SINGLE_2025_USD",
    "AMT_EXEMPTION_MFJ_2025_USD",
    "AMT_EXEMPTION_MFS_2025_USD",
    "AMT_PHASEOUT_START_SINGLE_2025_USD",
    "AMT_PHASEOUT_START_MFJ_2025_USD",
    "AMT_PHASEOUT_START_MFS_2025_USD",
    "AMT_RATE_BREAK_2025_USD",
    "AMT_RATE_BREAK_MFS_2025_USD",
)
