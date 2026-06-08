# U.S. 2025 Capital Gain Netting

## Authority

- `26 U.S.C. § 1211`
- `26 U.S.C. § 1212`
- `26 U.S.C. § 1256`
- Instructions for Schedule D (Form 1040)
- Instructions for Form 6781
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1040sd
  - https://www.irs.gov/instructions/i6781

## What This Rule Governs

The current `2025` U.S. capital workpaper:

- short-term and long-term bucket assembly
- Section 1256 `40/60` split
- final line `7a` capital amount

## Inputs

- Schwab capital buckets
- JPM stock-plan sales
- Coinbase gains/losses
- Section 1256 total

## Formula

1. aggregate short-term and long-term buckets
2. split Section `1256` result into `40%` short-term and `60%` long-term
3. compute net capital result
4. apply the selected filing-status annual capital-loss limit if net capital is negative

## Ordering

This applies before AGI, regular tax, NIIT, and FTC calculations.

## Rounding

- cents are preserved

## Edge Cases

- negative net capital
- loss cap
- carryforward

## Ambiguities / Filing Positions

The arithmetic is mechanical once basis/source facts are fixed. Separate factual positions can still exist for basis reconstruction.

## Implemented By

- `tax_pipeline/y2025/us_law.py:section_1256_split_2025`
- `tax_pipeline/y2025/us_law.py:compute_capital_assessment_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `capital_gain_or_loss_line_7a`
