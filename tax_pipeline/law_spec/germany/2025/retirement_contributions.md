# Germany 2025 Retirement Contributions

## Authority

- `§ 10 Abs. 1 Nr. 2 EStG`
- `§ 10 Abs. 3 Sätze 1 bis 6 EStG`
- `§ 3 Nr. 62 EStG`
- EStH 2025 Vorsorgeaufwendungen table
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__10.html
  - https://www.gesetze-im-internet.de/estg/__3.html
  - https://esth.bundesfinanzministerium.de/esth/2025/tabellarische-Uebersicht/Vorsorgeaufwendunge.html

## What This Rule Governs

Deductible retirement contributions in the current Germany `2025` model.

## Inputs

- employee pension contribution
- employer pension contribution

## Formula

1. add employee and employer pension contributions
2. cap the base at the 2025 `§ 10 Abs. 3 EStG` single-person maximum of `29,344 EUR`
3. for spouses assessed jointly, double the `§ 10 Abs. 3 Satz 2 EStG` cap before applying it to the joint contribution base
4. subtract total tax-free employer shares under `§ 10 Abs. 3 Sätze 5 bis 6 EStG` after the household cap is applied
5. allocate the resulting household deduction back to spouses only for audit display

## Ordering

This rule is part of special-expense computation before joint taxable income is finalized.

## Rounding

- cents are preserved

## Edge Cases

- the employer share is tracked for audit but not deducted a second time
- over-cap contribution facts are capped before employer-share subtraction
- joint assessment uses one doubled household cap, so contributions concentrated in one spouse do not incorrectly lose cap room
- uneven employer shares do not create extra deduction room because the total employer share is subtracted after the household cap

## Ambiguities / Filing Positions

None in the current implementation once the wage-certificate values are fixed.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:retirement_special_expense_deduction_2025`
- `tax_pipeline/y2025/germany_law.py:joint_retirement_special_expense_deductions_2025`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py:test_joint_retirement_cap_is_doubled_household_cap_under_10_3_estg`
- `tests/test_germany_2025_law.py:test_joint_retirement_cap_subtracts_total_employer_share_after_cap_under_10_3_estg`

## Outputs Affected

- `person_*_employer_pension_contribution`
- `person_*_employee_pension_contribution`
- `person_*_retirement_contributions`
