"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 164 (Deductible taxes)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164&num=0&edition=prelim
contains:
  - § 164(f)(1): one-half of § 1401 SE tax (OASDI + Medicare, excluding
    § 1401(b)(2) Additional Medicare) is allowed as an above-the-line
    deduction in computing AGI. Lands on Schedule 1 line 15 (and reduces
    Form 1040 line 10 / line 11 AGI). The arithmetic is performed inside
    ``adjusted_gross_income_2025`` (see ``p63.py`` and the
    ``us25_07_agi`` rule); this file is the citation anchor for that
    one-half deduction.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:efed478990b033808ccb19fa443a7c85e0cf488c674b471450a7b5a6e4195be4
---
"""
# Shadow extraction of § 164 citation surface (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.us_law``: § 164(f) is consumed by AGI's one-half
# SE-tax deduction parameter rather than owning its own helper, so this
# file exposes only the citation URL.
#
# Authority: 26 U.S.C. § 164 — taxes deductible at the federal level
# (state/local income, foreign income, real-property, personal-property,
# and § 164(f) one-half SE tax).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164
from __future__ import annotations

USC_164_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section164&num=0&edition=prelim"
)

__all__ = ("USC_164_URL",)
