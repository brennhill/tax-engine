"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 3101 (FICA tax — Additional Medicare 0.9 %)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101&num=0&edition=prelim
contains:
  - § 3101(b)(2): 0.9 % Additional Medicare Tax on wages above filing-
    status threshold ($200k Single/HoH, $250k MFJ, $125k MFS).
    Statutory thresholds are NOT inflation-indexed.
  - The companion § 1401(b)(2) 0.9 % Additional Medicare on SE earnings
    shares the same threshold (Form 8959 Part III combines wages + SE).
  - Combined assessment helper ``additional_medicare_assessment_2025``
    accepts wages and SE-taxable-earnings and returns the combined
    Form 8959 line-7/13/18 result.
numeric_constants:
  - ADDITIONAL_MEDICARE_RATE: 0.009                          # § 3101(b)(2)
  - ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD: 200000    # § 3101(b)(2)(C)
  - ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD: 250000       # § 3101(b)(2)(A)
  - ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD: 125000       # § 3101(b)(2)(B)
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:b1a04c54bbbdbc41c145744fcd085383a801d739380b533011154b04f030b298
---
"""
# Shadow extraction of § 3101(b)(2) Additional Medicare 0.9 % (Phase 2
# leaf §). Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte. Form 8959
# Part III combines the § 1401(b)(2) SE side and § 3101(b)(2) wage side
# under a single threshold.
#
# Authority: 26 U.S.C. § 3101(b)(2) — additional Medicare on wages.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import ZERO_USD, _require_non_negative, round_cents

# Re-use production dataclass so equality holds against orig outputs.
from tax_pipeline.y2025.us_law import USAdditionalMedicareAssessment2025

USC_3101_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section3101&num=0&edition=prelim"
)
IRS_FORM_8959_URL = "https://www.irs.gov/forms-pubs/about-form-8959"

# 26 U.S.C. § 3101(b)(2) / § 1401(b)(2) — 0.9 % Additional Medicare Tax.
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
ADDITIONAL_MEDICARE_RATE = _CONSTANTS["ADDITIONAL_MEDICARE_RATE"]
# § 3101(b)(2)(A)-(C) — statutory thresholds; NOT inflation-indexed.
ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD = _CONSTANTS["ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD"]
ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD = _CONSTANTS["ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD"]
ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD = _CONSTANTS["ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD"]


def _additional_medicare_threshold_2025(filing_status_label: str) -> Decimal:
    text = (filing_status_label or "").strip().lower()
    if text == "single":
        return ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD
    if text == "married filing jointly":
        return ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD
    if text == "married filing separately":
        return ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD
    raise NotImplementedError(
        "Additional Medicare threshold not implemented for U.S. filing "
        f"status {filing_status_label!r}; expected 'Single', 'Married "
        "filing jointly', or 'Married filing separately'."
    )


def additional_medicare_assessment_2025(
    *,
    filing_status_label: str,
    medicare_taxable_wages_usd: Decimal,
    se_taxable_earnings_usd: Decimal,
) -> USAdditionalMedicareAssessment2025:
    """Compute § 3101(b)(2) + § 1401(b)(2) Additional Medicare tax.

    Authority:
      - 26 U.S.C. § 3101(b)(2) — 0.9 % additional Medicare tax on wages
        above filing-status threshold.
      - 26 U.S.C. § 1401(b)(2) — same 0.9 % on SE earnings, sharing the
        same threshold (single threshold across wages + SE per
        Form 8959 Part III).
      - Form 8959 instructions — combined wage/SE base.

    URLs: see ``USC_3101_URL`` and ``IRS_FORM_8959_URL``.
    """
    _require_non_negative(
        medicare_taxable_wages_usd, label="medicare_taxable_wages_usd"
    )
    _require_non_negative(
        se_taxable_earnings_usd, label="se_taxable_earnings_usd"
    )
    threshold = _additional_medicare_threshold_2025(filing_status_label)
    combined = round_cents(medicare_taxable_wages_usd + se_taxable_earnings_usd)
    excess = round_cents(max(ZERO_USD, combined - threshold))
    addtl_tax = round_cents(excess * ADDITIONAL_MEDICARE_RATE)
    return USAdditionalMedicareAssessment2025(
        threshold_usd=threshold,
        medicare_wages_usd=round_cents(medicare_taxable_wages_usd),
        se_taxable_earnings_usd=round_cents(se_taxable_earnings_usd),
        combined_base_usd=combined,
        excess_over_threshold_usd=excess,
        additional_medicare_tax_usd=addtl_tax,
    )


__all__ = (
    "USC_3101_URL",
    "IRS_FORM_8959_URL",
    "ADDITIONAL_MEDICARE_RATE",
    "ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD",
    "ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD",
    "ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD",
    "additional_medicare_assessment_2025",
)
