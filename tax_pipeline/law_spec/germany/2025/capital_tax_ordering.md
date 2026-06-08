# Germany 2025 Capital Tax Ordering

## Authority

- `§ 32d Abs. 1 EStG`
- `§ 32d Abs. 5 EStG`
- `§ 4 SolzG 1995`
- `InvStG § 20`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__32d.html
  - https://www.gesetze-im-internet.de/solzg_1995/__4.html
  - https://www.gesetze-im-internet.de/invstg_2018/__20.html

## What This Rule Governs

The ordering of:

- Teilfreistellung
- capital income tax
- statutory foreign-tax credit, capped per item/source under § 32d Abs. 5 EStG
- capital solidarity surcharge
- explicit rejection of separate Germany treaty-position dividend credits unless they are modeled through the statutory foreign-tax-credit path

for the `2025` Germany capital-income model.

## Inputs

- `taxable_after_teilfreistellung_eur`
- `explicit_foreign_tax_total_eur`
- `foreign_tax_credit_cap_eur`
- `treaty_dividend_credit_eur`

## Formula

1. Apply Teilfreistellung to reach `taxable_after_teilfreistellung_eur`.
2. Compute capital income tax at `25%`.
3. Match foreign tax to individual taxable capital items by `foreign_tax_item_id` when provided, falling back to legacy symbol matching only for unambiguous older inputs.
4. Cap explicit foreign tax per individual taxable capital item/source under § 32d Abs. 5 EStG, after reducing paid tax by any refund entitlement. Do not pro-rate the individual item/source cap by the Sparer-Pauschbetrag.
5. Credit the capped total against capital income tax, capped again at the remaining gross capital tax after the § 20 Abs. 9 allowance.
6. Compute capital solidarity surcharge at `5.5%` of the remaining capital income tax, disregarding fractions of a cent under `§ 4 SolzG 1995`.
7. Reject any nonzero separate Germany treaty-position dividend credit as unsupported to avoid double-counting the statutory foreign-tax credit.

## Ordering

The ordering is explicit and material. The current code treats it as:

`Teilfreistellung -> 25% tax -> per-item §32d(5) foreign-tax cap -> statutory foreign-tax credit -> capital soli -> reject separate treaty dividend credit unless zero`

## Rounding

- income-tax and credit amounts are rounded to cents
- capital solidarity surcharge truncates/floors fractional cents

## Edge Cases

- per-item/source foreign-tax credit cannot exceed 25% of the individual taxable foreign capital item
- same-symbol foreign capital items cannot be pooled when item IDs are present
- same-symbol fallback without item IDs is accepted only when exactly one taxable item and one foreign-tax row use that symbol
- refund/reduction entitlements reduce creditable foreign tax before the per-item cap
- a U.S.-source treaty dividend item cannot also be claimed as a generic `foreign_tax` row with the same `foreign_tax_item_id`; that would create two § 32d Abs. 5 credit paths for one dividend item
- total foreign-tax credit cannot exceed the gross capital income tax
- separate Germany treaty dividend credit must be zero in this model

## Ambiguities / Filing Positions

The treaty credit amount remains visible as an explicit tax-position input, but nonzero values fail closed. Treaty relief must be represented through the § 32d(5) credit path or implemented as a separate law-backed calculation before being included.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:compute_germany_capital_assessment_2025`
- `tax_pipeline/y2025/germany_law.py:capital_tax_after_foreign_tax_credit_2025`
- `tax_pipeline/y2025/germany_law.py:foreign_tax_credit_32d5_cap_2025`
- `tax_pipeline/y2025/germany_law.py:treaty_relieved_capital_tax_2025`
- `tax_pipeline/pipelines/y2025/germany_model.py` consumes the typed capital assessment without recomputing tax stages

## Test Coverage

- `tests/test_germany_2025_law.py:test_capital_assessment_exposes_law_ordered_core_stages`
- `tests/test_germany_2025_law.py:test_fund_cash_income_is_not_double_counted_after_invstg_20_teilfreistellung`
- `tests/test_germany_2025_law.py:test_us_treaty_dividend_item_rejects_duplicate_generic_foreign_tax_row`
- `tests/test_germany_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-results.json capital.capital_income_tax_with_teilfreistellung_eur`
- `years/<year>/outputs/analysis-steps/germany-model-results.json capital.capital_tax_with_teilfreistellung_before_treaty_eur`
- `years/<year>/outputs/analysis-steps/germany-model-results.json capital.capital_tax_with_teilfreistellung_after_treaty_eur`
- `years/<year>/outputs/analysis-steps/germany-model-trace.csv capital_*`
