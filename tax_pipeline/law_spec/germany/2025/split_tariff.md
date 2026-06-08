# Germany 2025 Split Tariff

## Authority

- `§ 26b EStG`
- `§ 32a Abs. 5 EStG`
- Dated 2025 authority for constants:
  - https://www.bundesfinanzministerium.de/Datenportal/Daten/frei-nutzbare-produkte/Anwendungen/Programmablaufplan-2025/Programmablaufplan-2025.html
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__26b.html
  - https://www.gesetze-im-internet.de/estg/__32a.html

## What This Rule Governs

The joint income-tax tariff for two jointly assessed spouses in `2025`.

## Inputs

- `joint_taxable_income_eur`

## Formula

1. Divide joint taxable income by `2`.
2. Apply the `2025` single-person tariff to the halved amount.
3. Double the resulting tax.

The single-person tariff uses the official `2025` bracket constants and formulas from `§ 32a Abs. 1 EStG`. The implementation pins the dated BMF Programmablaufplan 2025 because live statute pages can show later-year constants.

## Ordering

This applies after:

- employment-income netting
- `§ 22 Nr. 3` inclusion
- all allowed special-expense deductions

It applies before:

- solidarity surcharge
- `§ 36` payment crediting

## Rounding

- taxable income is floored to full euros inside the tariff function
- resulting tax is floored to full euros

## Edge Cases

- if taxable income is at or below the ground allowance, income tax is `0`
- only the jointly assessed two-person case is supported by the current implementation

## Ambiguities / Filing Positions

None in the current implementation. This rule is treated as fully mechanical once `joint_taxable_income_eur` is fixed.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:german_income_tax_single_2025`
- `tax_pipeline/y2025/germany_law.py:german_income_tax_split_2025`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py`
- `tests/test_law_spec.py:test_germany_2025_tariff_and_soli_specs_pin_dated_bmf_authority`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-results.json ordinary.joint_income_tax_eur`
- `years/<year>/outputs/analysis-steps/germany-model-trace.csv joint_income_tax`
