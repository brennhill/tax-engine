# Germany 2025 Other Income Under Section 22 Number 3

## Authority

- `§ 22 Nr. 3 EStG`
- Official URL:
  - https://www.gesetze-im-internet.de/estg/__22.html

## What This Rule Governs

The threshold treatment for miscellaneous income currently used for staking income in the `2025` Germany model.

## Inputs

- `other_income_22nr3_eur`
- `other_income_22nr3_threshold_eur`

## Formula

This rule is implemented as a `Freigrenze`:

- if the annual amount reaches or exceeds the threshold, the full amount is taxable
- otherwise the taxable amount is `0`
- for joint assessment, the Freigrenze is applied per spouse to that spouse's own `§ 22 Nr. 3` income before aggregation

## Ordering

The taxable `§ 22 Nr. 3` amount is added after income-by-category aggregation and before the final joint taxable-income calculation.

## Rounding

- cents are preserved

## Edge Cases

- exact threshold boundary
- zero amount
- missing per-spouse allocations in a joint return fail closed when the aggregate amount is nonzero

## Ambiguities / Filing Positions

The current model assumes the Coinbase staking amount belongs in this bucket. That classification is a separate legal/factual posture; the threshold arithmetic itself is mechanical once the bucketed amount is fixed.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:other_income_22nr3_taxable_2025`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`
- `tax_pipeline/y2025/germany_inputs.py:load_joint_ordinary_inputs_2025`

## Test Coverage

- `tests/test_germany_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-results.json refunds.other_income_22nr3_taxable_eur`
- `years/<year>/outputs/analysis-steps/germany-model-trace.csv other_income_22nr3_taxable`
