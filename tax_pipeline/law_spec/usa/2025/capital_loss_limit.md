# U.S. 2025 Capital Loss Limit

## Authority

- `26 U.S.C. § 1211`
- `26 U.S.C. § 1212`
- Instructions for Schedule D (Form 1040)
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1040sd

## What This Rule Governs

The annual filing-status-specific capital-loss deduction limit and carryforward treatment in the `2025` U.S. capital workpaper.

## Inputs

- net capital result after bucket assembly
- filing-status-specific annual capital-loss cap

## Formula

- if net capital is positive, Form `1040` line `7a` takes the full net amount
- if net capital is negative, the current-year deduction is capped at the selected filing-status limit (`3000 USD` generally, `1500 USD` for married filing separately)
- any remaining loss becomes carryforward

## Ordering

This applies after Schedule D / Form 8949 / Section `1256` netting and before AGI / NIIT / regular-tax assembly.

## Rounding

- cents are preserved in the workpaper layer

## Edge Cases

- zero net capital
- net capital loss smaller than the selected filing-status cap
- net capital loss larger than the selected filing-status cap

## Ambiguities / Filing Positions

None in the current implementation once filing status is fixed.

## Implemented By

- `tax_pipeline/y2025/us_law.py:compute_capital_assessment_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-estimate.json`
- `years/<year>/outputs/analysis-steps/us-capital-results.json`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv capital_gain_or_loss_line_7a`
