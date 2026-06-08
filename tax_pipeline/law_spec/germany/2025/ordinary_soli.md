# Germany 2025 Ordinary Solidarity Surcharge

## Authority

- `§ 3 SolzG 1995`
- `§ 4 SolzG 1995`
- Dated 2025 authority for constants:
  - https://www.bundesfinanzministerium.de/Datenportal/Daten/frei-nutzbare-produkte/Anwendungen/Programmablaufplan-2025/Programmablaufplan-2025.html
- Official URLs:
  - https://www.gesetze-im-internet.de/solzg_1995/__3.html
  - https://www.gesetze-im-internet.de/solzg_1995/__4.html

## What This Rule Governs

The solidarity surcharge on ordinary German income-tax assessments.

## Inputs

- assessed ordinary income tax
- filing posture (`single`, `married_separate`, or `married_joint`)

## Formula

1. Select the 2025 exemption threshold: `19,950 EUR` for single/separate assessments or `39,900 EUR` for splitting assessments. The implementation pins this to the dated BMF Programmablaufplan 2025 because live statute pages can show later-year thresholds.
2. If the assessed income tax is at or below the selected exemption threshold, surcharge is `0`.
3. Otherwise compute:
   - the raw surcharge at `5.5%`
   - the mitigation-zone amount
4. The final surcharge is the smaller of those two amounts.

## Ordering

This applies after the ordinary income tax is computed and before `§ 36` payment crediting.

## Rounding

- fractions of a cent are disregarded under `§ 4 SolzG 1995`
- the implementation truncates/floors ordinary solidarity surcharge amounts to cents

## Edge Cases

- threshold boundary cases
- mitigation-zone cases where the mitigation amount is less than the raw `5.5%` amount

## Ambiguities / Filing Positions

None in the current implementation. This rule is treated as fully mechanical once the assessed income tax and filing posture are fixed.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:german_soli_assessment_2025`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py`
- `tests/test_law_spec.py:test_germany_2025_tariff_and_soli_specs_pin_dated_bmf_authority`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/germany-model-results.json ordinary.joint_solidarity_surcharge_eur`
- `years/<year>/outputs/analysis-steps/germany-model-trace.csv joint_solidarity_surcharge`
