"""
---
jurisdiction: TREATY
treaty: DBA-USA (Germany–United States Convention for the Avoidance of Double Taxation, Income and Capital, signed 1989, amended 2006 Protocol)
tax_year: 2025
statute: DBA-USA Art. 23(5)(b) implemented via IRS Publication 514 (Foreign Tax Credit for Individuals)
url: https://www.irs.gov/publications/p514
contains:
  - Pub. 514 worksheet line 16: U.S. tax on the U.S.-source dividend stack
    measured at the average regular-tax rate (regular tax / taxable
    income); F-FN-2 fix uses taxable income (Form 1040 line 15), not AGI
  - Pub. 514 worksheet line 17: treaty-allowed source-country tax (15 %
    rate under DBA-USA Art. 10(2)(b))
  - Pub. 514 worksheet line 18: U.S. tax above the treaty floor (max of
    0 and line 16 minus line 17)
  - Pub. 514 worksheet line 19: max of 0 and line 16 minus the greater of
    (line 17 treaty floor, the German residence credit on the same
    U.S.-source dividend stack)
  - Pub. 514 worksheet line 20c: max of 0 and Germany's pre-credit
    residence tax minus the same greater-of clamp
  - Pub. 514 worksheet line 21: lesser of line 19 and line 20c
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:fa617f810f17f38ba132c0bbd1079922218cbed562be7bce42b85ecd862fd30b
---
"""
# Shadow extraction of IRS Pub. 514 average-tax-rate worksheet helpers
# (Phase 5 cross-jurisdictional treaty math). Mirrors
# ``tax_pipeline.y2025.treaty_rules`` byte-for-byte for the two rule
# bodies that consume both U.S. taxable income and Germany's residence-
# country precredit / residence-credit on the same dividend stack:
# ``treaty25_16_average_tax_floor`` and ``treaty25_17_german_residual_cap``.
#
# These helpers are intentionally a separate file from the per-Article
# citation files (art10/art11/art17/art23/art28) because the worksheet
# logic crosses jurisdictions — it imports both Germany-side and
# U.S.-side facts — and would not audit cleanly under either jurisdiction
# alone.
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.y2025.us_law import USTreatyInputs2025, round_cents

ZERO_USD = Decimal("0.00")


def _treaty_inputs(facts: Mapping[str, Any]) -> USTreatyInputs2025:
    treaty_inputs = facts["us.treaty.inputs"]
    if not isinstance(treaty_inputs, USTreatyInputs2025):
        raise TypeError("us.treaty.inputs must be a USTreatyInputs2025 instance")
    return treaty_inputs


def treaty25_16_average_tax_floor(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pub. 514 worksheet lines 16/17/18 — average-rate U.S. tax floor.

    Authority:
    - DBA-USA Art. 10(2)(b) (15 % treaty rate)
    - DBA-USA Art. 23(5)(b) (treaty re-sourcing)
    - IRS Publication 514 (https://www.irs.gov/publications/p514)
    """
    # Pub. 514 worksheet line 16: U.S. tax on the U.S.-source dividend stack
    # measured at the average regular-tax rate. Per IRS Publication 514,
    # the "Average rate" is regular tax divided by **taxable income**
    # (Form 1040 line 15), NOT adjusted gross income; AGI as the divisor
    # systematically understates the rate because AGI > taxable income
    # whenever a deduction (standard or itemized) applies. F-FN-2 in the
    # 2026-05-01 per-function review documents the prior AGI denominator
    # as a low-bias drift; this implementation uses taxable income to
    # conform to the worksheet.
    # Pub. 514 worksheet line 17: treaty-allowed source-country tax (15 % rate
    # under DBA-USA Art. 10 paragraph 2(b)).
    # Pub. 514 worksheet line 18: U.S. tax above the treaty floor (max of
    # 0 and line 16 minus line 17). Line 19 (computed in TREATY25-17) further
    # clips this by the German residence credit when that credit exceeds the
    # 15 % floor.
    # https://www.irs.gov/publications/p514
    from tax_pipeline.y2025.us_law import (
        validate_germany_treaty_dividend_coverage_2025,
    )

    treaty_inputs = _treaty_inputs(facts)
    if not treaty_inputs.use_treaty_resourcing:
        return {
            "treaty.us_tax_on_us_source_dividends": ZERO_USD,
            "treaty.treaty_minimum_us_tax_at_source": ZERO_USD,
            "treaty.us_limitation_above_15_percent_floor": ZERO_USD,
        }

    us_source_dividends = Decimal(str(facts["treaty.us_source_dividends"]))
    regular_tax_before_credits = Decimal(str(facts["us.stage.regular_tax_before_credits"]))
    taxable_income = Decimal(str(facts["us.stage.taxable_income"]))
    treaty_dividend_rate = Decimal(str(facts["us.constants.treaty_dividend_rate"]))

    if taxable_income <= ZERO_USD:
        raise ValueError("us.stage.taxable_income must be positive for the Pub. 514 average-rate worksheet")

    us_tax_average_rate = regular_tax_before_credits / taxable_income
    us_tax_on_us_source_dividends = round_cents(us_tax_average_rate * us_source_dividends)
    treaty_minimum_us_tax_at_source = round_cents(us_source_dividends * treaty_dividend_rate)
    validate_germany_treaty_dividend_coverage_2025(
        us_source_dividends_usd=us_source_dividends,
        treaty_allowed_us_tax_at_source_usd=treaty_minimum_us_tax_at_source,
        treaty_inputs=treaty_inputs,
    )
    us_limitation_above_15_percent_floor = round_cents(
        max(ZERO_USD, us_tax_on_us_source_dividends - treaty_minimum_us_tax_at_source)
    )
    return {
        "treaty.us_tax_on_us_source_dividends": us_tax_on_us_source_dividends,
        "treaty.treaty_minimum_us_tax_at_source": treaty_minimum_us_tax_at_source,
        "treaty.us_limitation_above_15_percent_floor": us_limitation_above_15_percent_floor,
    }


def treaty25_17_german_residual_cap(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pub. 514 worksheet lines 19/20c — German residual-residence-tax cap.

    Authority:
    - DBA-USA Art. 23 (residence-country relief)
    - IRS Publication 514 (https://www.irs.gov/publications/p514)
    """
    # Pub. 514 worksheet line 19 (re-derived): max of 0 and line 16 minus the
    # greater of (line 17 treaty floor, the German residence credit on the same
    # U.S.-source dividend stack). When the residence credit exceeds the 15 %
    # floor, line 19 < line 18; line 21 (TREATY25-18) uses line 19, not line 18.
    # Pub. 514 worksheet line 20c: max of 0 and Germany's pre-credit residence
    # tax on the same dividends minus the same greater-of clamp. Caps the
    # additional credit by residual residence-country tax under DBA-USA Art. 23.
    treaty_inputs = _treaty_inputs(facts)
    if not treaty_inputs.use_treaty_resourcing:
        return {
            "treaty.worksheet_line_19_maximum_credit": ZERO_USD,
            "treaty.german_residual_cap": ZERO_USD,
            "treaty.german_precredit_tax_on_us_source_dividends": ZERO_USD,
            "treaty.german_residence_credit_for_us_tax": ZERO_USD,
        }

    us_tax_on_us_source_dividends = Decimal(str(facts["treaty.us_tax_on_us_source_dividends"]))
    treaty_minimum_us_tax_at_source = Decimal(str(facts["treaty.treaty_minimum_us_tax_at_source"]))
    germany = facts["de.treaty.us_source_dividend_tax_and_credit"]
    # Per CLAUDE.md "never silently default to zero": when treaty re-sourcing is
    # enabled (gated above), the upstream U.S. core validator
    # (``us_2025_law._validate_treaty_dividend_coverage``) already raises
    # ValueError if either German precredit tax or residence credit is None,
    # and the producer in ``treaty_initial_facts_2025`` always populates both
    # sub-dict keys. Subscripting (rather than ``.get(..., ZERO_USD)``) ensures
    # any future producer-contract violation surfaces as a KeyError under
    # invariant I4 instead of silently denying the additional FTC (review H5).
    german_precredit = round_cents(
        Decimal(str(germany["german_precredit_tax_on_us_source_dividends_usd"]))
    )
    residence_credit = round_cents(
        Decimal(str(germany["german_residence_credit_for_us_tax_usd"]))
    )
    floor_or_residence = max(treaty_minimum_us_tax_at_source, residence_credit)
    worksheet_line_19 = round_cents(
        max(ZERO_USD, us_tax_on_us_source_dividends - floor_or_residence)
    )
    worksheet_line_20c = round_cents(
        max(ZERO_USD, german_precredit - floor_or_residence)
    )
    return {
        "treaty.worksheet_line_19_maximum_credit": worksheet_line_19,
        "treaty.german_residual_cap": worksheet_line_20c,
        "treaty.german_precredit_tax_on_us_source_dividends": german_precredit,
        "treaty.german_residence_credit_for_us_tax": residence_credit,
    }
