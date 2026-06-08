# Germany 2025 Basic Tariff

## Authority

- `§ 32a Abs. 1 EStG`
- Dated 2025 authority for constants:
  - https://www.bundesfinanzministerium.de/Datenportal/Daten/frei-nutzbare-produkte/Anwendungen/Programmablaufplan-2025/Programmablaufplan-2025.html
- Live statute URL:
  - https://www.gesetze-im-internet.de/estg/__32a.html

## What This Rule Governs

The basic German income-tax tariff for a single assessment or a separately assessed spouse in `2025`.

## Formula

Apply the `2025` `§ 32a Abs. 1 EStG` bracket formula to taxable income after flooring to full euros. The implementation pins the 2025 constants from the dated BMF Programmablaufplan because live statute pages can show later-year values.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:german_income_tax_single_2025`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py:test_split_tariff_uses_2025_statutory_thresholds`
- `tests/test_law_spec.py:test_germany_2025_tariff_and_soli_specs_pin_dated_bmf_authority`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-results.json ordinary.joint_income_tax_eur`
- `years/<year>/outputs/analysis-steps/germany-model-trace.csv joint_income_tax`
