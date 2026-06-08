"""
---
jurisdiction: US
tax_year: 2025
statute: Rev. Proc. 2024-40 § 3.05
url: https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
contains:
  - § 3.05: 2025 inflation-adjusted Additional Child Tax Credit (ACTC)
    refundable cap per qualifying child under 26 U.S.C. § 24(d)(1)(A) /
    § 24(h)(2). The TCJA-era $1,700 refundable cap is preserved for 2025
    by the One Big Beautiful Bill Act (OBBBA) and published by the IRS
    in Rev. Proc. 2024-40.
numeric_constants:
  - CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD: 1700
amended_by:
  - One Big Beautiful Bill Act (OBBBA) — preserves $1,700 refundable cap
  - Rev. Proc. 2024-40 (2025 inflation update) — § 3.05
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:6951ae1b3ba4aead06db68eff7849767113ef7dfa20b8f821b17601d98dee013
---
"""
# Shadow extraction of the Rev. Proc. 2024-40 § 3.05 ACTC refundable cap
# (Phase 5 — Rev. Proc. inflation tables). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The IRC § 24 file at
# ``law/usa/year_2025/usc26/p24.py`` imports this constant rather than
# duplicating it, so future inflation roll-forward (Rev. Proc. 2025-XX
# § 3.05) updates this single file without touching the IRC § 24 body.
#
# Authority: Rev. Proc. 2024-40 § 3.05; published by the IRS at
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf. Schedule 8812 (2025)
# instructions cite this same $1,700 refundable cap per qualifying child.
# https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

# Refundable Additional Child Tax Credit (ACTC) cap per qualifying child.
# 26 U.S.C. § 24(d)(1)(A) / § 24(h)(2) — Rev. Proc. 2024-40 § 3.05 sets the
# 2025 refundable cap at $1,700. Schedule 8812 (2025) instructions echo
# this value. If a future statute raises this cap, update this constant
# AND the law spec entry — the test suite pins the numeric value so a
# silent change cannot land.
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
# https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD = _CONSTANTS["CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD"]

__all__ = ("CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD",)
