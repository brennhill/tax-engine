# U.S. 2025 Regular Tax

## Authority

- `26 U.S.C. § 1`
- Instructions for Form `1040`
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1040gi

## What This Rule Governs

The ordinary-bracket component of the `2025` U.S. regular tax for the currently selected filing posture.

## Inputs

- `taxable_income_usd`
- `qualified_dividends_usd`
- net capital gain eligible for preferential rates
- 2025 ordinary-bracket thresholds from structured U.S. tax constants

## Formula

1. Remove qualified dividends and net capital gain from taxable income to reach taxable ordinary income.
2. If the relevant worksheet says to figure tax on an amount below `$100,000`, use the IRS Tax Table mechanics for the selected filing posture.
3. For amounts of `$100,000` or more, apply the `2025` Tax Computation Worksheet / ordinary brackets selected by filing posture.
4. Combine ordinary tax with the qualified-dividends-and-capital-gain worksheet result.

## Ordering

This is computed before:

- FTCs
- NIIT
- payment reconciliation

It is combined with the qualified-dividend component to reach regular tax before credits.

## Rounding

- Tax Table results are whole-dollar table amounts
- computation-worksheet and preferential-rate components preserve cents in the supporting workpaper layer

## Edge Cases

- taxable income may be reduced by qualified dividends down to zero ordinary taxable income
- Tax Table treatment applies below `$100,000`
- upper-bracket transitions depend on the selected 2025 filing-posture thresholds

## Ambiguities / Filing Positions

The bracket logic itself is mechanical once filing status and taxable income are fixed. The loader maps `single`, `married_joint`, and `married_separate` posture constants into the stable law-core dataclass shape.

## Implemented By

- `tax_pipeline/y2025/us_law.py:tax_from_schedule_y2_2025`
- `tax_pipeline/y2025/us_law.py:regular_tax_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-estimate.json tax.ordinary_tax_component_usd`
- `years/<year>/outputs/analysis-steps/us-tax-estimate.json tax.regular_tax_before_credits_usd`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv regular_tax_before_credits`
