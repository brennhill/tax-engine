"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 63 (Taxable income defined)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63&num=0&edition=prelim
contains:
  - § 63(b): taxable income for non-itemizers = AGI − standard deduction
  - § 63(c): standard deduction (the 2025 dollar amount lives in
    ``USTaxConstants2025.standard_deduction_2025_usd``, sourced from
    ``years/<year>/normalized/reference-data/us-tax-constants.csv``).
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:2de934114af7537f2d9d56dfce6ed83ee8c114625ca5f29fa8e1aaf2fab45055
---
"""
# Shadow extraction of § 63 EStG taxable-income subtraction (Phase 2
# leaf §). Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte. The
# 2025 standard-deduction amount is loaded from the reference-data CSV
# (per filing posture) into ``USTaxConstants2025.standard_deduction_2025_usd``;
# this file therefore exposes the citation anchor and the
# ``taxable_income_2025`` subtraction helper that consumes it.
#
# Authority: 26 U.S.C. § 63(b)/(c) — taxable income / standard deduction.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63
from __future__ import annotations

from decimal import Decimal

USC_63_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section63&num=0&edition=prelim"
)


def taxable_income_2025(
    adjusted_gross_income_usd: Decimal,
    standard_deduction_2025_usd: Decimal,
) -> Decimal:
    """26 U.S.C. § 63(b) taxable-income subtraction.

    Returns ``max(0, AGI − standard_deduction)``. The 2025 standard
    deduction amount is supplied by the caller from the loaded
    ``USTaxConstants2025`` (filing-posture-specific row of
    ``years/<year>/normalized/reference-data/us-tax-constants.csv``).

    Authority: 26 U.S.C. § 63(b) (taxable income for non-itemizers).
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63
    """
    return max(Decimal("0.00"), adjusted_gross_income_usd - standard_deduction_2025_usd)


__all__ = ("USC_63_URL", "taxable_income_2025")
