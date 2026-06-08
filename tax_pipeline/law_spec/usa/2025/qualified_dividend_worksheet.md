# U.S. 2025 Qualified Dividends and Capital Gain Tax Worksheet

## Authority

- `26 U.S.C. § 1(h)`
- Instructions for Form `1040`
- Schedule `D`
- IRS Publication `550`
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1040gi
  - https://www.irs.gov/publications/p550

## What This Rule Governs

The reduced-rate regular-tax treatment for qualified dividends and net capital gain in the current `2025` U.S. model.

## Inputs

- `taxable_income_usd`
- `qualified_dividends_usd`, which must be a subset of ordinary dividends reported on Form 1040 line 3b
- net capital gain for the line-16 worksheet, derived from the smaller of positive Schedule D line `15` and positive Schedule D line `16`
- 2025 filing-status qualified-dividend thresholds from structured U.S. tax constants

## Formula

1. Compute line `4` preferential income as qualified dividends plus net capital gain.
2. Compute line `5` taxable ordinary income as taxable income minus line `4`.
3. Fill the `0%` bucket up to the filing-status zero-rate ceiling.
4. Fill the `15%` bucket up to the filing-status fifteen-rate ceiling.
5. Tax any remaining preferential income at `20%`.
6. Compare that preferential-rate tax with ordinary tax on all taxable income and use the lower amount.

The net capital gain input includes long-term stock gains, capital gain distributions, and the `60%` long-term share of Section `1256` contracts. It excludes short-term gains and loss-limited negative capital results.

## Ordering

This rule runs inside the regular-tax computation and is combined with the ordinary-bracket tax component.

## Rounding

- cents are preserved

## Edge Cases

- all preferential income can fall into the zero-rate band
- some or all can overflow into the `15%` or `20%` bands
- short-term gains remain ordinary-rate income
- the Section `1256` `40%` short-term share remains ordinary-rate income while the `60%` long-term share enters the preferential worksheet
- qualified dividends cannot exceed ordinary dividends; Form 1040 line 3a is a subset of line 3b

## Ambiguities / Filing Positions

None in the current arithmetic once taxable income, qualified dividends, and filing status are fixed.

## Implemented By

- `tax_pipeline/y2025/us_law.py:regular_tax_2025`

## Test Coverage

- `tests/test_us_2025_law.py`
- `tests/test_us_2025_law.py:test_qualified_dividends_must_be_subset_of_ordinary_dividends`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-estimate.json tax.qualified_dividend_tax_component_usd`
- `years/<year>/outputs/analysis-steps/us-tax-estimate.json tax.regular_tax_before_credits_usd`
