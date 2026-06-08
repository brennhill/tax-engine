# Germany 2025 Assessment Ordering

## Authority

- `§ 2 Abs. 2 bis 6 EStG`
- `§ 26 EStG`
- `§ 26b EStG`
- `§ 32a Abs. 5 EStG`
- `§ 36 Abs. 2 EStG`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__2.html
  - https://www.gesetze-im-internet.de/estg/__26.html
  - https://www.gesetze-im-internet.de/estg/__26b.html
  - https://www.gesetze-im-internet.de/estg/__32a.html
  - https://www.gesetze-im-internet.de/estg/__36.html

## What This Rule Governs

The overall legal order of the ordinary Germany assessment in the current `2025` model.

## Inputs

- all ordinary-income facts
- `§ 22 Nr. 3` other income
- ordinary deductions and special expenses
- withholding and prepayment facts

## Formula

This is an ordering rule, not a single formula:

1. determine income by category
2. determine whether § 26 EStG permits and elects joint assessment
3. under § 26b EStG, aggregate spouse income for joint assessment only after each spouse's income is identified
4. subtract Werbungskosten where applicable
5. aggregate remaining income
6. subtract special expenses
7. determine joint taxable income
8. apply the appropriate § 32a tariff
9. apply ordinary solidarity surcharge
10. credit withholding and prepayments

## Ordering

This file exists specifically to make the legal order explicit.

## Rounding

- taxable-income and tariff rounding are handled in the more specific rule files

## Edge Cases

- none beyond the component rules

## Ambiguities / Filing Positions

None in the ordering itself. Ambiguities live inside the component rules.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`
- `tax_pipeline/pipelines/y2025/germany_model.py`

## Test Coverage

- `tests/test_germany_2025_law.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-trace.csv joint_assessment_order`
- all downstream ordinary Germany outputs
