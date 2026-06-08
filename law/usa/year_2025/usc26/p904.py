"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 904 (Foreign Tax Credit limitation)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
contains:
  - § 904(a): per-basket limitation =
    pre-credit U.S. tax × (foreign-source taxable income / worldwide
    taxable income), capped at the pre-credit U.S. tax.
  - § 904(b)(1): worldwide taxable income (Form 1040 line 15) is the
    fraction's denominator. The current model uses the documented-
    positive-income subset under ``conservative_positive_income_only``
    (rejected to a single posture in ``validate_supported_us_filing_positions_2025``).
  - § 904(c): carryforward / carryback rules (1-year back, 10-year
    forward — modeled at the rule layer; constants live in the
    composition).
  - Helpers:
      ``ftc_limitation_2025`` — per-basket § 904(a) ceiling
      ``standard_deduction_allocation_2025`` — Form 1116 deduction
        allocation between baskets
      ``total_gross_income_for_ftc_2025`` — documented-positive-income
        denominator builder
      ``validate_documented_positive_income_denominator_bound_2025`` —
        § 904(b)(1) ceiling check
      ``current_year_general_foreign_tax_usd_2025`` — Pub. 514 wage-share
        allocation of joint German wage-side tax
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:0685a2d2d5aa6e46978e312818e992d589fd1441c4580850cc8f4d2ffbfd6622
---
"""
# Shadow extraction of § 904 FTC limitation helpers (Phase 2 leaf §).
# Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte. The credit-
# allowance selection (``allowed_ftc_2025``) lives at § 901 in
# ``p901.py``; this file owns the limitation and its supporting
# allocation helpers.
#
# Authority: 26 U.S.C. § 904 — limitation on foreign tax credit.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
# https://www.irs.gov/instructions/i1116
# https://www.irs.gov/publications/p514
from __future__ import annotations

from decimal import Decimal

from law._utils.money import ZERO_USD, _require_non_negative, _require_positive, round_cents

USC_904_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section904&num=0&edition=prelim"
)


def total_gross_income_for_ftc_2025(
    *,
    wages_usd: Decimal,
    ordinary_dividends_usd: Decimal,
    interest_income_usd: Decimal,
    schedule_1_other_income_usd: Decimal,
    capital_gain_distributions_usd: Decimal,
    known_positive_short_capital_gain_usd: Decimal,
    known_positive_long_capital_gain_usd: Decimal,
) -> Decimal:
    # FTC expense allocation under 26 U.S.C. § 904 and the Form 1116 instructions depends on
    # category gross income. The current model keeps the conservative documented-positive-income
    # denominator as the only supported 2025 posture. Unsupported alternatives are rejected in
    # validate_supported_us_filing_positions_2025() before the law core runs.
    #
    # § 904(b) deviation note: 26 U.S.C. § 904(b)(1) and Form 1116 line 18 conventions
    # use worldwide taxable income as the FTC fraction's denominator, with the gross-income
    # variant only as a deduction-allocation step. This module's documented-positive-income
    # denominator is conservative for the credit fraction but can drift if positive items
    # are double-counted or if the documented subset ever exceeds the
    # (taxable income + standard deduction) ceiling. The companion
    # ``validate_documented_positive_income_denominator_bound_2025`` helper enforces the
    # ceiling at ``compute_ftc_assessment_2025`` time so the deviation cannot silently
    # invert. See https://www.irs.gov/instructions/i1116 (Part III, line 18) and
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
    return round_cents(
        wages_usd
        + ordinary_dividends_usd
        + interest_income_usd
        + schedule_1_other_income_usd
        + capital_gain_distributions_usd
        + known_positive_short_capital_gain_usd
        + known_positive_long_capital_gain_usd
    )


def validate_documented_positive_income_denominator_bound_2025(
    *,
    total_gross_income_for_ftc_usd: Decimal,
    taxable_income_usd: Decimal,
    standard_deduction_usd: Decimal,
) -> None:
    # 26 U.S.C. § 904(b)(1) wants worldwide taxable income (Form 1040 line 15) as the
    # FTC fraction's denominator. The 2025 model uses the documented-positive-income
    # subset under ``conservative_positive_income_only`` (rejected to a single posture in
    # ``validate_supported_us_filing_positions_2025``). That subset is always <= worldwide
    # gross income, which itself equals taxable income + standard deduction (1040 line 12)
    # under the only supported posture (no Schedule A itemizers in this model). The
    # binding assertion here makes the invariant explicit so the deviation cannot
    # silently invert (e.g., if a future fact-extraction change ever double-counted a
    # positive item) and over-allocate deductions to a basket.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
    # https://www.irs.gov/instructions/i1116
    _require_non_negative(total_gross_income_for_ftc_usd, label="total_gross_income_for_ftc_usd")
    _require_non_negative(taxable_income_usd, label="taxable_income_usd")
    _require_non_negative(standard_deduction_usd, label="standard_deduction_usd")
    worldwide_gross_income_ceiling = round_cents(taxable_income_usd + standard_deduction_usd)
    if total_gross_income_for_ftc_usd > worldwide_gross_income_ceiling:
        # Imported lazily to avoid a module-load-time cycle with core/stages.py.
        from tax_pipeline.core.stages import LegalInvariantViolation

        raise LegalInvariantViolation(
            "US25-11-FTC-DENOMINATOR",
            "Documented-positive-income FTC denominator "
            f"{total_gross_income_for_ftc_usd} exceeds the worldwide-gross-income "
            f"ceiling {worldwide_gross_income_ceiling} = taxable_income_usd "
            f"({taxable_income_usd}) + standard_deduction_usd ({standard_deduction_usd}). "
            "26 U.S.C. § 904(b)(1) requires the FTC fraction denominator to be bounded "
            "by worldwide taxable income; under the only supported 2025 posture (no "
            "Schedule A itemizers), the documented-positive-income subset must remain "
            "<= taxable_income + standard_deduction. Investigate whether a positive "
            "income item is being double-counted before relaxing this bound."
        )


def standard_deduction_allocation_2025(
    *,
    standard_deduction_usd: Decimal,
    category_gross_income_usd: Decimal,
    total_gross_income_for_ftc_usd: Decimal,
) -> Decimal:
    # Form 1116 instructions and Publication 514 require allocating deductions between baskets.
    _require_non_negative(standard_deduction_usd, label="standard_deduction_usd")
    _require_non_negative(category_gross_income_usd, label="category_gross_income_usd")
    if total_gross_income_for_ftc_usd < ZERO_USD:
        raise ValueError("total_gross_income_for_ftc_usd must be non-negative")
    if total_gross_income_for_ftc_usd == ZERO_USD:
        if category_gross_income_usd != ZERO_USD:
            raise ValueError(
                "category_gross_income_usd must also be zero when total_gross_income_for_ftc_usd is zero"
            )
        return Decimal("0.00")
    if category_gross_income_usd == ZERO_USD:
        return Decimal("0.00")
    return standard_deduction_usd * (category_gross_income_usd / total_gross_income_for_ftc_usd)


def ftc_limitation_2025(
    *,
    regular_tax_before_credits_usd: Decimal,
    category_taxable_income_usd: Decimal,
    taxable_income_usd: Decimal,
) -> Decimal:
    # 26 U.S.C. § 904(a) limits the credit to "the same proportion of the tax against
    # which such credit is taken which the taxpayer's taxable income from sources without
    # the United States ... bears to his entire taxable income for the same taxable year."
    # Form 1116 line 21 implements this as min(line 19, line 20) — i.e. the FTC for the
    # basket cannot exceed the pre-credit U.S. tax. When the taxpayer has U.S.-source
    # losses, foreign-source taxable income can exceed worldwide taxable income, which
    # would push the unbounded fraction above 1.0 and overstate the credit. Cap at the
    # pre-credit U.S. tax to honor the statutory ceiling.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
    # https://www.irs.gov/instructions/i1116 (Part III, line 21)
    # https://www.irs.gov/publications/p514
    _require_non_negative(regular_tax_before_credits_usd, label="regular_tax_before_credits_usd")
    _require_non_negative(category_taxable_income_usd, label="category_taxable_income_usd")
    if taxable_income_usd < ZERO_USD:
        raise ValueError("taxable_income_usd must be non-negative")
    if taxable_income_usd == ZERO_USD:
        if category_taxable_income_usd != ZERO_USD:
            raise ValueError(
                "category_taxable_income_usd must also be zero when taxable_income_usd is zero"
            )
        return Decimal("0.00")
    if category_taxable_income_usd == ZERO_USD:
        return Decimal("0.00")
    return min(
        regular_tax_before_credits_usd,
        regular_tax_before_credits_usd * (category_taxable_income_usd / taxable_income_usd),
    )


def current_year_general_foreign_tax_usd_2025(
    *,
    taxpayer_gross_wages_eur: Decimal,
    spouse_gross_wages_eur: Decimal,
    joint_wage_side_tax_eur: Decimal,
    eur_per_usd_yearly_average_2025: Decimal,
    use_full_joint_tax: bool = False,
) -> Decimal:
    # Publication 514 allows allocation of joint foreign tax by relative foreign-source income.
    # The current model supports only the explicit wage-share allocation posture; unsupported
    # alternatives are rejected before the law core runs.
    _require_non_negative(taxpayer_gross_wages_eur, label="taxpayer_gross_wages_eur")
    _require_non_negative(spouse_gross_wages_eur, label="spouse_gross_wages_eur")
    denominator = taxpayer_gross_wages_eur + spouse_gross_wages_eur
    _require_non_negative(joint_wage_side_tax_eur, label="joint_wage_side_tax_eur")
    _require_positive(eur_per_usd_yearly_average_2025, label="eur_per_usd_yearly_average_2025")
    if denominator == ZERO_USD:
        if joint_wage_side_tax_eur == ZERO_USD:
            return ZERO_USD
        raise ValueError("joint German wage denominator must be positive when joint wage-side tax is non-zero")
    if use_full_joint_tax:
        return round_cents(joint_wage_side_tax_eur / eur_per_usd_yearly_average_2025)
    taxpayer_share = taxpayer_gross_wages_eur / denominator
    return round_cents((joint_wage_side_tax_eur * taxpayer_share) / eur_per_usd_yearly_average_2025)


__all__ = (
    "USC_904_URL",
    "total_gross_income_for_ftc_2025",
    "validate_documented_positive_income_denominator_bound_2025",
    "standard_deduction_allocation_2025",
    "ftc_limitation_2025",
    "current_year_general_foreign_tax_usd_2025",
)
