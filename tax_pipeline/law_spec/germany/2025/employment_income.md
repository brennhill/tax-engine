# Germany 2025 Employment Income

## Authority

- `§ 19 Abs. 1 EStG`
- `§ 2 Abs. 2 Satz 1 Nr. 2 EStG`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__19.html
  - https://www.gesetze-im-internet.de/estg/__2.html

## What This Rule Governs

Employment income before and after Werbungskosten in the current `2025` Germany model.

## Inputs

- wage-certificate gross wage facts
- allowed Werbungskosten

## Formula

`income_after_werbungskosten = gross_wage - allowed_werbungskosten`

## Ordering

This applies before special expenses and before joint aggregation.

## Rounding

- cents are preserved

## Edge Cases

- if actual expenses are below the Arbeitnehmer-Pauschbetrag, the allowed expense amount comes from the allowance rule instead

## Ambiguities / Filing Positions

None in the arithmetic. Wage facts come from the extracted wage certificates.

## Implemented By

- `tax_pipeline/y2025/germany_inputs.py:_load_wage_totals`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py`

## Outputs Affected

- `person_*_gross_wage`
- `person_*_income_after_werbungskosten`
- `sum_income_after_werbungskosten`

