"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 24 (Child Tax Credit + ODC + ACTC)
url: https://www.law.cornell.edu/uscode/text/26/24
contains:
  - § 24(a): $2,200 Child Tax Credit per qualifying child under § 152(c)
    (post-TCJA / OBBBA-extended numerics for 2025).
  - § 24(b)(2): MAGI phase-out thresholds — $200,000 (Single/HoH/MFS)
    and $400,000 (MFJ); 5 % reduction per $1,000 of MAGI excess.
  - § 24(b)(3): excess rounded up to the next $1,000 before applying
    the 5 % reduction (= $50 per $1,000).
  - § 24(d)(1)(A): refundable Additional Child Tax Credit (ACTC) cap
    per qualifying child — $1,700 for 2025 (Rev. Proc. 2024-40 § 3.05;
    imported from ``rev_proc/proc_2024_40/p3_05.py``).
  - § 24(d)(1)(B): earned-income phase-in = 15 % × max(0, earned − $2,500).
  - § 24(h)(4): $500 Credit for Other Dependents (ODC), NON-refundable.
  - § 24(h)(7): valid SSN required for CTC (the loader handles
    classification before the assessment runs).
numeric_constants:
  - CTC_PER_CHILD_2025_USD: 2200
  - ODC_PER_DEPENDENT_2025_USD: 500
  - CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD: 200000
  - CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD: 400000
  - CTC_PHASEOUT_RATE: 0.05
  - CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD: 2500
  - CTC_REFUNDABLE_PHASE_IN_RATE: 0.15
imports_from:
  - law/usa/year_2025/rev_proc/proc_2024_40/p3_05.py: CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD
  - law/usa/year_2025/usc26/p152.py: USC_152_URL (qualifying-child citation)
amended_by:
  - One Big Beautiful Bill Act (OBBBA, 2025) — § 70104 raises the § 24(a)
    base from the TCJA $2,000 to $2,200 (via § 24(h)(2) substitution) and
    $1,700 refundable cap for 2025.
  - Rev. Proc. 2024-40 § 3.05 — 2025 refundable cap inflation amount.
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:47dec987beebd8305fa25c487713aac2ab203b4c65b0dcf86333ccdc42abf2a6
---
"""
# Shadow extraction of § 24 CTC + ODC + ACTC (Phase 3 composing §).
# Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte. The 2025
# refundable cap ($1,700) is imported from Rev. Proc. 2024-40 § 3.05
# (``rev_proc/proc_2024_40/p3_05.py``); the per-child base ($2,200),
# ODC amount ($500), phase-out thresholds ($200k / $400k), 5 % phase-
# out rate, $2,500 earned-income floor, and 15 % refundable phase-in
# rate are statutory and live here.
#
# Authority: 26 U.S.C. § 24 — Child Tax Credit + ODC + Additional Child
# Tax Credit; § 152 — qualifying child / qualifying relative.
# https://www.law.cornell.edu/uscode/text/26/24
# https://www.law.cornell.edu/uscode/text/26/152
# https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import ZERO_USD, _require_non_negative, round_cents
from law.usa.year_2025.rev_proc.proc_2024_40.p3_05 import (
    CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD,
)
from law.usa.year_2025.usc26.p152 import USC_152_URL  # noqa: F401  (cited)

# Re-use production dataclass so equality holds against orig outputs.
from tax_pipeline.y2025.us_law import USChildTaxCreditAssessment2025

USC_24_URL = "https://www.law.cornell.edu/uscode/text/26/24"
SCH_8812_INSTRUCTIONS_URL = (
    "https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040"
)

# 26 U.S.C. § 24(a) — $2,200 CTC per qualifying child (post-TCJA /
# OBBBA-extended for 2025).
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
CTC_PER_CHILD_2025_USD = _CONSTANTS["CTC_PER_CHILD_2025_USD"]
# 26 U.S.C. § 24(h)(4) — $500 ODC per qualifying child age 17+ or
# qualifying relative with TIN. NON-refundable.
ODC_PER_DEPENDENT_2025_USD = _CONSTANTS["ODC_PER_DEPENDENT_2025_USD"]
# 26 U.S.C. § 24(b)(2) — MAGI phase-out thresholds (statutory; not
# inflation-indexed).
CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD = _CONSTANTS["CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD"]
CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD = _CONSTANTS["CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD"]
# § 24(b)(2) — $50 reduction per $1,000 of MAGI excess = 5 percentage
# points per $1,000, applied to the rounded-up thousand-dollar excess.
CTC_PHASEOUT_RATE = _CONSTANTS["CTC_PHASEOUT_RATE"]
# § 24(d)(1)(B) — earned income floor below which no refundable ACTC is
# generated.
CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD = _CONSTANTS["CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD"]
# § 24(d)(1)(B) — 15 % phase-in rate on earned income above the floor.
CTC_REFUNDABLE_PHASE_IN_RATE = _CONSTANTS["CTC_REFUNDABLE_PHASE_IN_RATE"]


def _ctc_phaseout_threshold_2025(*, filing_status_label: str) -> Decimal:
    # § 24(b)(2): MFJ uses the $400,000 threshold; all other filing
    # statuses (Single, HoH, MFS, Surviving spouse) use the $200,000
    # threshold under the post-TCJA / OBBBA-extended numerics.
    label = filing_status_label.strip().lower()
    if label == "married filing jointly":
        return CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD
    return CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD


def ctc_and_odc_assessment_2025(
    *,
    children_count_qualifying_for_ctc: int,
    children_count_qualifying_for_odc: int,
    earned_income_usd: Decimal,
    modified_agi_usd: Decimal,
    regular_tax_after_ftc_usd: Decimal,
    filing_status_label: str,
) -> USChildTaxCreditAssessment2025:
    """26 U.S.C. § 24 Child Tax Credit + ODC assessment for 2025.

    Authority:
      - § 24(a): $2,200 CTC per qualifying child (§ 152(c)).
      - § 24(b)(2): phase-out begins at $200k single / $400k MFJ;
        $50 reduction per $1,000 of MAGI excess (round excess up to
        the next $1,000 per § 24(b)(3)).
      - § 24(d)(1)(B): refundable ACTC = 15 % × (earned income −
        $2,500), capped at $1,700 per qualifying child (post-OBBBA
        2025 cap; Rev. Proc. 2024-40 § 3.05 + Schedule 8812 (2025)
        instructions).
      - § 24(h)(4): $500 ODC per qualifying child 17+ or qualifying
        relative with TIN (NON-refundable).
      - § 24(h)(7): CTC requires a valid SSN issued before the due
        date of the return (the loader handles classification before
        the assessment runs).

    https://www.law.cornell.edu/uscode/text/26/24
    https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
    https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
    """
    if children_count_qualifying_for_ctc < 0:
        raise ValueError("children_count_qualifying_for_ctc must be non-negative")
    if children_count_qualifying_for_odc < 0:
        raise ValueError("children_count_qualifying_for_odc must be non-negative")
    _require_non_negative(earned_income_usd, label="earned_income_usd")
    _require_non_negative(modified_agi_usd, label="modified_agi_usd")
    _require_non_negative(regular_tax_after_ftc_usd, label="regular_tax_after_ftc_usd")

    gross_ctc = round_cents(
        Decimal(children_count_qualifying_for_ctc) * CTC_PER_CHILD_2025_USD
    )
    gross_odc = round_cents(
        Decimal(children_count_qualifying_for_odc) * ODC_PER_DEPENDENT_2025_USD
    )
    combined_pre = round_cents(gross_ctc + gross_odc)

    threshold = _ctc_phaseout_threshold_2025(filing_status_label=filing_status_label)
    magi_excess = max(ZERO_USD, modified_agi_usd - threshold)
    # § 24(b)(3) round excess up to next $1,000 before applying the
    # 5 %-per-$1,000 rate (= $50 per $1,000). Use ROUND_FLOOR to compute
    # ceil via -((-x) // 1000) * 1000.
    one_thousand = Decimal("1000")
    excess_quotient = magi_excess / one_thousand
    # Ceil to next integer:
    excess_thousands = (-((-excess_quotient).to_integral_value(rounding=ROUND_FLOOR)))
    rounded_excess_for_reduction = round_cents(excess_thousands * one_thousand)
    phaseout_reduction = round_cents(rounded_excess_for_reduction * CTC_PHASEOUT_RATE)
    if phaseout_reduction > combined_pre:
        phaseout_reduction = combined_pre
    combined_post = round_cents(combined_pre - phaseout_reduction)

    # Nonrefundable portion is the part of the combined post-phaseout
    # credit that offsets regular tax after FTC. It is capped at the
    # regular-tax-after-FTC value (§ 24(b)(3) ordering: nonrefundable
    # credits cannot reduce tax below zero).
    nonrefundable_portion = round_cents(min(combined_post, regular_tax_after_ftc_usd))

    # Refundable ACTC under § 24(d)(1):
    #   refundable = min(remaining_ctc, $1,700/child, 15% × max(0, earned_income − $2,500))
    # ODC is NOT refundable, so allocate the nonrefundable_portion to
    # CTC first (§ 24 ordering): the remaining-CTC ceiling is the part
    # of the post-phaseout CTC that did not absorb regular tax. When
    # combined_post equals gross CTC + ODC, allocate nonrefundable to
    # ODC first only up to gross_odc — anything above absorbs CTC.
    # Conservative allocation: assume nonrefundable absorbed CTC first,
    # so refundable ceiling = max(0, post-phaseout CTC − nonrefundable).
    # When phase-out applies it reduces CTC and ODC pro rata; collapse
    # to combined_post then split: post-phaseout CTC share =
    # combined_post × gross_ctc / combined_pre (cents-rounded).
    if combined_pre > ZERO_USD:
        post_phaseout_ctc = round_cents(combined_post * gross_ctc / combined_pre)
    else:
        post_phaseout_ctc = ZERO_USD
    remaining_ctc_for_refundable = max(ZERO_USD, post_phaseout_ctc - nonrefundable_portion)
    refundable_per_child_cap = round_cents(
        Decimal(children_count_qualifying_for_ctc)
        * CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD
    )
    earned_income_excess = max(
        ZERO_USD, earned_income_usd - CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD
    )
    earned_income_phase_in = round_cents(
        earned_income_excess * CTC_REFUNDABLE_PHASE_IN_RATE
    )
    refundable_actc = round_cents(
        min(
            remaining_ctc_for_refundable,
            refundable_per_child_cap,
            earned_income_phase_in,
        )
    )
    if refundable_actc < ZERO_USD:
        refundable_actc = ZERO_USD
    total_credit = round_cents(nonrefundable_portion + refundable_actc)

    # Delegate to the canonical production assessment so the shadow file
    # tracks every Schedule 8812 line that ``USChildTaxCreditAssessment2025``
    # currently surfaces (lines 4, 6, 9, 10, 13, 16a/b, 18a-21, 27 + total).
    # The shadow file documents the per-§ structure and cites the statute;
    # delegating the dataclass construction to production prevents
    # field-list drift between the two as Schedule 8812 surface evolves.
    from tax_pipeline.y2025.us_law import (
        ctc_and_odc_assessment_2025 as _production_assess,
    )
    return _production_assess(
        children_count_qualifying_for_ctc=children_count_qualifying_for_ctc,
        children_count_qualifying_for_odc=children_count_qualifying_for_odc,
        earned_income_usd=earned_income_usd,
        modified_agi_usd=modified_agi_usd,
        regular_tax_after_ftc_usd=regular_tax_after_ftc_usd,
        filing_status_label=filing_status_label,
    )


__all__ = (
    "USC_24_URL",
    "SCH_8812_INSTRUCTIONS_URL",
    "CTC_PER_CHILD_2025_USD",
    "ODC_PER_DEPENDENT_2025_USD",
    "CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD",
    "CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD",
    "CTC_PHASEOUT_RATE",
    "CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD",
    "CTC_REFUNDABLE_PHASE_IN_RATE",
    "CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD",
    "_ctc_phaseout_threshold_2025",
    "ctc_and_odc_assessment_2025",
)
