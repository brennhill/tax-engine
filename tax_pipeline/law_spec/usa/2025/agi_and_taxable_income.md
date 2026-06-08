# U.S. 2025 AGI And Taxable Income

## Authority

- `26 U.S.C. § 61`
- `26 U.S.C. § 63`
- Instructions for Form `1040`
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1040gi

## What This Rule Governs

The current `2025` U.S. AGI and taxable-income assembly.

## Inputs

- wages
- ordinary dividends
- interest
- Schedule 1 other income
- Form `1040` line `7a`
- standard deduction

## Formula

1. AGI is assembled from the gross-income components used in the current model.
2. Taxable income is AGI minus the selected filing-status standard deduction, not below zero.

## Ordering

This applies after capital `line 7a` is known and before regular tax, FTC limitations, and NIIT.

## Rounding

- cents are preserved

## Edge Cases

- taxable income cannot go below zero

## Ambiguities / Filing Positions

The current model includes explicit positions on which items belong in Schedule 1 other income. Once that classification is fixed, the AGI/taxable-income arithmetic is mechanical.

## Implemented By

- `tax_pipeline/y2025/us_law.py:adjusted_gross_income_2025`
- `tax_pipeline/y2025/us_law.py:taxable_income_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `adjusted_gross_income`
- `taxable_income`
