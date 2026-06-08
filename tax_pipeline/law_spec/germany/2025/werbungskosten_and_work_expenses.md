# Germany 2025 Werbungskosten And Work Expenses

## Authority

- `§ 9 Abs. 1 EStG`
- `§ 9 Abs. 5 EStG`
- `§ 4 Abs. 5 Satz 1 Nr. 6c EStG`
- `§ 9a Satz 1 Nr. 1 Buchst. a EStG`
- `§ 6 Abs. 2 EStG` for the GWG immediate-expensing shortcut
- BMF wage-tax guidance on work-related tax-advice allocation
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__9.html
  - https://www.gesetze-im-internet.de/estg/__4.html
  - https://www.gesetze-im-internet.de/estg/__9a.html
  - https://www.gesetze-im-internet.de/estg/__6.html
  - https://ao.bundesfinanzministerium.de/esth/2025/B-Anhaenge/Anhang-16/XIII/inhalt.html

## What This Rule Governs

Employment-related deductions currently modeled as Werbungskosten:

- work equipment
- home-office daily allowance
- telecom deduction
- work-related legal insurance
- work-related share of cross-border tax-advice costs
- Arbeitnehmer-Pauschbetrag comparison

## Inputs

- equipment source amounts
- work-use shares from config
- home-office day counts from config
- telecom, legal-insurance, and tax-advice factual allocations from config

## Formula

1. for work equipment, use the gross amount directly only inside the `§ 6 Abs. 2 EStG` GWG shortcut; above that threshold, require a source-fact current-year AfA/deductible amount
2. multiply the current-year deductible equipment amount by work-use share
3. compute home-office `Tagespauschale`, counting days with a first-workplace visit only when an explicit no-other-workplace position is present
4. add all employment-related deductions
5. compare total actual Werbungskosten to the Arbeitnehmer-Pauschbetrag capped at that spouse's employment receipts
6. use the larger amount

## Ordering

This applies before computing employment income after Werbungskosten.

## Rounding

- equipment shares and deduction amounts are rounded to cents

## Edge Cases

- work-use share must be between `0` and `1`
- negative day counts are invalid
- actual Werbungskosten can be lower than the statutory allowance
- first-workplace visit days fail closed unless the no-other-workplace condition is explicitly confirmed
- the Arbeitnehmer-Pauschbetrag cannot create an artificial employment loss when wage receipts are lower than the lump sum
- high-value durable equipment fails closed unless the facts layer provides the current-year deductible amount

## Ambiguities / Filing Positions

Several inputs here are explicit factual allocations rather than parser-derived amounts:

- current-year AfA/deductible amount for high-value equipment
- work-use shares
- telecom deduction
- legal-insurance work share
- tax-advice work share

The arithmetic is mechanical once those factual positions are fixed.

## Implemented By

- `tax_pipeline/y2025/germany_inputs.py:_load_work_equipment_items_by_person`
- `tax_pipeline/y2025/germany_law.py:home_office_tagespauschale_2025`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py:test_high_value_equipment_requires_current_year_deduction_under_9_and_6_estg`
- `tests/test_germany_2025_law.py`

## Outputs Affected

- `person_*_equipment_*`
- `person_*_work_equipment`
- `person_*_home_office_deduction`
- `person_*_telecom_deduction`
- `person_*_employment_legal_insurance_deduction`
- `person_*_cross_border_tax_help_deduction`
- `person_*_actual_werbungskosten`
- `person_*_allowed_werbungskosten`
