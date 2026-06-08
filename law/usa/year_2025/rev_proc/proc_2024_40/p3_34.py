"""
---
jurisdiction: US
tax_year: 2025
statute: Rev. Proc. 2024-40 § 3.34
url: https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
contains:
  - § 3.34: 2025 inflation-adjusted Foreign Earned Income Exclusion
    annual ceiling under 26 U.S.C. § 911(b)(2)(D).
numeric_constants:
  - SECTION_911_FEIE_2025_USD: 130000
amended_by:
  - Rev. Proc. 2024-40 (2025 inflation update) — § 3.34
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:b5c16079d715c9871e4d4456f29b1ce1768e62bc7f7cac7e96263227b88b0677
---
"""
# Shadow extraction of the Rev. Proc. 2024-40 § 3.34 FEIE ceiling
# (Phase 5 — Rev. Proc. inflation tables). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The IRC § 911 file at
# ``law/usa/year_2025/usc26/p911.py`` imports this constant rather than
# duplicating it, so future inflation roll-forward (Rev. Proc. 2025-XX
# § 3.34) updates this single file without touching the IRC § 911 body.
#
# Authority: 26 U.S.C. § 911(b)(2)(D); annual inflation amount published
# by the IRS in Rev. Proc. 2024-40 (Internal Revenue Bulletin 2024-43).
# The 16 % base-housing rate (§ 911(c)(1)(B)) and 30 % housing-cost
# ceiling rate (§ 911(c)(2)(A)) are statutory and live with the § 911
# file (they are not Rev. Proc. inflation amounts).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

# 26 U.S.C. § 911(b)(2)(D) annual base FEIE ceiling for 2025: $130,000
# (Rev. Proc. 2024-40 § 3.34). § 911(c)(1)(B) base housing amount = 16 %
# of FEIE ($20,800 for 2025). § 911(c)(2)(A) caps the housing-cost
# ceiling at 30 % of the § 911 exclusion ($39,000 default for 2025)
# before the IRS Notice 2024-77 location adjustment.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SECTION_911_FEIE_2025_USD = _CONSTANTS["SECTION_911_FEIE_2025_USD"]

__all__ = ("SECTION_911_FEIE_2025_USD",)
