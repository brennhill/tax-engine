"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 1211 (Limitation on capital losses)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211&num=0&edition=prelim
contains:
  - § 1211(b): individual taxpayer's capital-loss deduction is limited
    to the lesser of (1) the excess of capital losses over capital gains
    or (2) $3,000 ($1,500 for MFS).
numeric_constants:
  - STANDARD_CAPITAL_LOSS_LIMIT_USD: 3000.00  # § 1211(b)
  - MFS_CAPITAL_LOSS_LIMIT_USD: 1500.00       # § 1211(b)(2)
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:6871dda85c24e34e622f2f9ea680aa21297134afe4b4dc8b59451901892c4a3f
---
"""
# Shadow extraction of § 1211 capital-loss-limit constants (Phase 2
# leaf §). Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte. The
# dollar figures are statutory (not inflation-indexed), so they live
# directly in this file rather than in a Rev. Proc. inflation table.
# The arithmetic that consumes these constants lives in
# ``compute_capital_assessment_2025`` (a § 1211/§ 1212-driven helper
# that is part of the larger capital-buckets composition).
#
# Authority: 26 U.S.C. § 1211(b) — limitation on capital losses.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

USC_1211_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1211&num=0&edition=prelim"
)

# 26 U.S.C. § 1211(b) — individual capital-loss deduction limited to
# $3,000 ($1,500 MFS) of net capital loss against ordinary income.
# Statutory constants; not inflation-indexed.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
MFS_CAPITAL_LOSS_LIMIT_USD = _CONSTANTS["MFS_CAPITAL_LOSS_LIMIT_USD"]
STANDARD_CAPITAL_LOSS_LIMIT_USD = _CONSTANTS["STANDARD_CAPITAL_LOSS_LIMIT_USD"]

__all__ = (
    "USC_1211_URL",
    "MFS_CAPITAL_LOSS_LIMIT_USD",
    "STANDARD_CAPITAL_LOSS_LIMIT_USD",
)
