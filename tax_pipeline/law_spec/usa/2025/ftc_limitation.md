# U.S. 2025 Foreign Tax Credit Limitation

## Authority

- `26 U.S.C. § 901`
- `26 U.S.C. § 904`
- Instructions for Form `1116`
- IRS Publication `514`
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1116
  - https://www.irs.gov/publications/p514

## What This Rule Governs

The limitation arithmetic for passive and general foreign tax credits in the `2025` U.S. model.

## Inputs

- `regular_tax_before_credits_usd`
- `taxable_income_usd`
- category taxable income for passive and general baskets
- foreign-source qualified dividends
- foreign-source net capital gain
- current-year foreign tax by basket
- carryovers by basket

## Formula

Before computing the limitation, the engine checks whether Form `1116` line `18` can use unadjusted taxable income. If the return has foreign-source qualified dividends or foreign-source net capital gain and the IRS adjustment exception is unavailable, the engine fails closed because the Worksheet for Line `18` reduction is not implemented yet.

For each basket:

`limitation = regular_tax_before_credits * category_taxable_income / taxable_income`

Allowed FTC is the lesser of:

- basket limitation
- current-year foreign tax plus carryover

## Ordering

1. compute category gross income
2. allocate the standard deduction
3. compute category taxable income
4. compute limitation
5. compute allowed basket credit
6. sum allowed credits

## Rounding

- cents are preserved

## Edge Cases

- zero or negative taxable income
- zero category income
- carryovers larger than the limitation
- foreign preferential income below the IRS adjustment-exception threshold
- foreign preferential income requiring the Worksheet for Line `18`

## Ambiguities / Filing Positions

The arithmetic is mechanical once the basket inputs are fixed.

The current model still relies on explicit filing positions for:

- positive-income-only FTC denominator posture
- wage-share allocation of joint German wage-side tax
- electing the Form `1116` qualified-dividend/capital-gain adjustment exception when eligible

Those positions affect the inputs, not the limitation formula itself.

The engine does not implement the full Form `1116` Worksheet for Line `18`. When foreign-source qualified dividends plus foreign-source net capital gain are at least `$20,000`, or when line `5` of the Qualified Dividends and Capital Gain Tax Worksheet exceeds the IRS exception ceiling for the filing posture, it raises `NotImplementedError` rather than silently overstating the FTC limitation.

## Implemented By

- `tax_pipeline/y2025/us_law.py:total_gross_income_for_ftc_2025`
- `tax_pipeline/y2025/us_law.py:standard_deduction_allocation_2025`
- `tax_pipeline/y2025/us_law.py:ftc_limitation_2025`
- `tax_pipeline/y2025/us_law.py:validate_form_1116_preferential_adjustment_support_2025`
- `tax_pipeline/y2025/us_law.py:allowed_ftc_2025`
- `tax_pipeline/y2025/us_law.py:compute_ftc_assessment_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-estimate.json ftc.*`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv general_ftc_limitation`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv passive_ftc_limitation`
