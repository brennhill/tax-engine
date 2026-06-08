# Germany 2025 Health And Other Vorsorge

## Authority

- `§ 10 Abs. 1 Nr. 3 EStG`
- `§ 10 Abs. 1 Nr. 3a EStG`
- `§ 10 Abs. 4 EStG`
- `§ 10c EStG`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__10.html
  - https://www.gesetze-im-internet.de/estg/__10c.html

## What This Rule Governs

Basic health and nursing deductions, other Vorsorge cap treatment, and the final ordinary special-expense total in the current Germany `2025` model.

## Inputs

- employee health-insurance contribution
- employee nursing-care contribution
- employee unemployment-insurance contribution
- statutory sick-pay reduction rate
- each spouse's `§ 10 Abs. 4` cap class (`1,900 EUR` or `2,800 EUR`)
- deductible retirement contributions

## Formula

1. reduce statutory health insurance by the non-deductible sick-pay portion
2. add nursing-care contributions
3. determine remaining cap room for other Vorsorge
4. for spouses assessed jointly, compute the `§ 10 Abs. 4 Sätze 3 und 4 EStG` common cap from both spouses' individual caps and let basic health/nursing consume that common cap first
5. allow unemployment-insurance and similar items only to the extent the cap allows
6. sum deductible retirement contributions, health/nursing, and allowed other Vorsorge
7. add the `§ 10c` Sonderausgaben-Pauschbetrag separately for non-Vorsorge special expenses not otherwise modeled (`36 EUR` single/separate, `72 EUR` joint)

## Ordering

This applies after employment-income netting and before taxable income and tariff tax.

## Rounding

- cents are preserved

## Edge Cases

- invalid sick-pay reduction rates are rejected
- the `1,900 EUR` vs `2,800 EUR` § 10 Abs. 4 cap class is an explicit `people.csv` fact, not a loader default
- other Vorsorge can be reduced to zero if health/nursing already consumes the cap
- joint assessment sums each spouse's own `1,900 EUR` or `2,800 EUR` cap class into the statutory common cap
- people facts declaring statutory health insurance with sick-pay entitlement require the `4%` reduction under `§ 10 Abs. 1 Nr. 3 Satz 4 EStG`
- health/nursing contributions fail closed if the sick-pay entitlement fact is blank
- `§ 10c` is not a floor that replaces Vorsorge; it is a separate lump sum for other special-expense categories

## Ambiguities / Filing Positions

The current model uses explicit people facts to validate whether the sick-pay reduction applies. If future facts show a different non-deductible health-insurance share, the fact schema and validation rule would need a law-backed update.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:deductible_basic_health_contribution_2025`
- `tax_pipeline/y2025/germany_law.py:other_vorsorge_allowed_employee_2025`
- `tax_pipeline/y2025/germany_law.py:joint_other_vorsorge_allowed_employee_2025`
- `tax_pipeline/y2025/germany_inputs.py:_person_manual_deductions`
- `tax_pipeline/y2025/germany_law.py:compute_joint_ordinary_assessment_2025`

## Test Coverage

- `tests/test_germany_2025_law.py:test_joint_other_vorsorge_cap_is_common_cap_under_10_4_estg`
- `tests/test_germany_2025_law.py:test_joint_other_vorsorge_cap_sums_each_spouse_10_4_cap_class`
- `tests/test_germany_2025_law.py:test_statutory_sick_pay_people_fact_forces_10_1_3_sentence_4_reduction`
- `tests/test_germany_2025_law.py:test_health_contributions_require_explicit_sick_pay_fact_under_10_1_3_sentence_4_estg`
- `tests/test_germany_2025_law.py:test_other_vorsorge_cap_requires_explicit_people_fact_under_10_4_estg`

## Outputs Affected

- `person_*_health_gross`
- `person_*_health_sick_pay_reduction`
- `person_*_nursing_care`
- `person_*_health_and_nursing`
- `person_*_other_vorsorge_contributions`
- `person_*_other_vorsorge_allowed`
- `person_*_special_expenses_total`
- `joint_other_vorsorge_cap`
- `joint_other_vorsorge_health_nursing_consumed`
- `total_special_expenses`
