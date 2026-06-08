# U.S. 2025 Payments And Refund

## Authority

- Instructions for Form `1040`
- Official URL:
  - https://www.irs.gov/instructions/i1040gi

## What This Rule Governs

The final payment reconciliation in the current `2025` U.S. model, both baseline and treaty scenario.

## Inputs

- estimated payment
- total tax without treaty re-sourcing
- total tax with treaty re-sourcing

## Formula

- baseline result = estimated payment minus total tax
- treaty result = estimated payment minus treaty-scenario total tax

Positive means refund; negative means balance due.

## Ordering

This is the final assembly step on the U.S. side.

## Rounding

- cents are preserved

## Edge Cases

- refund or balance due can be positive, zero, or negative

## Ambiguities / Filing Positions

The arithmetic is mechanical. Treaty-scenario total tax can still depend on manual treaty-position inputs described elsewhere.

## Implemented By

- `tax_pipeline/y2025/us_law.py:compute_us_assessment_2025`
- `tax_pipeline/pipelines/y2025/us_model.py`

## Test Coverage

- `tests/test_us_2025_law.py`
- `tests/test_year_pipeline.py`

## Outputs Affected

- `refund_if_positive_else_balance_due`
- `refund_if_positive_else_balance_due_with_treaty_resourcing`

