# Germany 2025 Payments And Crediting

## Authority

- `§ 36 Abs. 2 EStG`
- Official URL:
  - https://www.gesetze-im-internet.de/estg/__36.html

## What This Rule Governs

Crediting withheld wage tax, withheld wage solidarity surcharge, and prepayments against the assessed ordinary tax.

## Inputs

- `withheld_wage_tax_eur`
- `withheld_wage_solidarity_surcharge_eur`
- `prepayments_eur`
- `joint_income_tax_eur`
- `joint_solidarity_surcharge_eur`

## Formula

1. sum each tax type of withholding across spouses
2. round each tax-type sum up to whole euros under `§ 36 Abs. 3 EStG`
3. preserve prepayments as actual EUR payment amounts
4. compute `ordinary_refund_before_capital_eur = rounded_withheld_wage_tax + rounded_withheld_wage_soli + prepayments - joint_income_tax - joint_solidarity_surcharge`

## Ordering

This rule applies after the ordinary tax and ordinary solidarity surcharge are fixed.

It does not itself govern the capital-income side.

## Rounding

- withholding credits are rounded up after summing each withholding-tax type
- prepayments are not rounded by this rule and must be explicit non-negative EUR amounts

## Edge Cases

- negative result means additional balance due on the ordinary side
- positive result means refund before any capital-income adjustments
- separate spouse withholding cents must not each round upward before aggregation
- negative or non-EUR German prepayment rows fail closed

## Ambiguities / Filing Positions

The rule is mechanical once withholding and prepayment facts are fixed. The factual question is whether the prepayment is actually on the tax office account; that is outside the arithmetic rule itself.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`
- `tax_pipeline/y2025/germany_inputs.py:_sum_document_fact`

## Test Coverage

- `tests/test_germany_2025_law.py:test_joint_wage_withholding_rounds_each_abzugsteuer_sum_under_36_3_estg`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-results.json ordinary.ordinary_refund_before_capital_eur`
- `years/<year>/outputs/analysis-steps/germany-model-trace.csv ordinary_refund_before_capital`
