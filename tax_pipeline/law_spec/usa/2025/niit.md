# U.S. 2025 Net Investment Income Tax

## Authority

- `26 U.S.C. § 1411`
- Instructions for Form `8960`
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411&num=0&edition=prelim
  - https://www.irs.gov/instructions/i8960

## What This Rule Governs

The `3.8%` net investment income tax in the current `2025` U.S. model.

## Inputs

- net investment income
- modified adjusted gross income
- selected NIIT threshold

## Formula

`NIIT = 3.8% * min(net investment income, MAGI excess over threshold)`

For a U.S. citizen/resident filing a regular joint return with an NRA spouse under a section 6013(g)/(h) election, Form 8960 instructions keep the NIIT threshold at married-filing-separately treatment unless the taxpayer separately elects joint treatment for NIIT.

## Ordering

This applies after AGI and the capital result are known and before final payment reconciliation.

## Rounding

- cents are preserved

## Edge Cases

- no NIIT when MAGI does not exceed the threshold
- no NIIT when net investment income is zero or negative

## Ambiguities / Filing Positions

The current model has an explicit filing position on whether staking income is included in NIIT.

The current model also has a distinct optional election for applying the joint-return NRA-spouse election to NIIT. The regular income-tax joint election does not automatically select the MFJ NIIT threshold.

Once that posture is fixed, the NIIT arithmetic itself is mechanical.

## Implemented By

- `tax_pipeline/y2025/us_law.py:niit_assessment_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-estimate.json tax.niit_usd`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv niit`
