"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 61 (Gross income defined)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61&num=0&edition=prelim
contains:
  - § 61(a): general definition of gross income (compensation, dividends,
    interest, etc.). The U.S. 2025 model carries this as a citation
    anchor for the gross-income components consumed by AGI in
    ``adjusted_gross_income_2025`` (housed under § 63 / Form 1040
    line 11) — § 61 itself does not own a math helper.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:43942fdec52afcc0dccb8f46e951a3cebfcf84d559ceeaccc6b04b14bf5e5187
---
"""
# Shadow extraction of § 61 EStG citation surface (Phase 2 leaf §). The
# § 61 file is cite-only because the production code anchors gross-income
# items at § 61 via comments but performs no math directly bound to § 61
# (the AGI computation lives at § 63 / § 164(f) — see ``p63.py`` and
# ``p164.py``). The citation URL constant is preserved so other shadow
# files import a single source of truth for the § 61 link.
#
# Authority: 26 U.S.C. § 61 — gross income defined.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
from __future__ import annotations

# 26 U.S.C. § 61 — gross income defined. Cited near the AGI computation
# (``adjusted_gross_income_2025``) where the income components attach.
USC_61_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section61&num=0&edition=prelim"
)

__all__ = ("USC_61_URL",)
