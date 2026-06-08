# Germany 2025 § 33 EStG außergewöhnliche Belastungen

## Authority

- `§ 33 EStG`, `§ 33 Abs. 3 EStG`
- Official URL: https://www.gesetze-im-internet.de/estg/__33.html
- BFH VI R 75/14, 19.01.2017 (slab progression on the brackets).

## What This Rule Governs

Deduction of extraordinary burdens (typically medical / Krankheitskosten) above the zumutbare Belastung. The zumutbare Belastung is a sliding scale of the Gesamtbetrag der Einkünfte (GdE) by family category, applied progressively (slab method).

## Inputs

- `de.ordinary.raw_inputs.medical_expenses_eur`
- `de.ordinary.raw_inputs.zumutbare_belastung_family_category`
- `de.ordinary.net_employment_income`
- `de.ordinary.other_income_22nr3_taxable`
- `de.ordinary.altersentlastungsbetrag` (the GdE = sum_income − § 24a allowance)

## Formula

For each family category in `ZUMUTBARE_BELASTUNG_2025_RATES`:

| Family category | GdE ≤ 15,340 | GdE ≤ 51,130 | GdE > 51,130 |
| --- | --- | --- | --- |
| `single_no_children` | 5 % | 6 % | 7 % |
| `joint_or_few_children` | 4 % | 5 % | 6 % |
| `many_children` | 1 % | 1 % | 2 % |

The slab arithmetic:

```
band_a = min(GdE, 15340)
band_b = max(0, min(GdE, 51130) - 15340)
band_c = max(0, GdE - 51130)
zumutbare_belastung = band_a*rate_a + band_b*rate_b + band_c*rate_c
deductible = max(0, medical_expenses - zumutbare_belastung)
```

## Ordering

`§ 33` is a Sonderausgaben-adjacent deduction; the implementation runs after the § 10c Sonderausgaben-Pauschbetrag at DE25-06B and before § 2 Abs. 5 zvE assembly at DE25-07.

## Rounding

- `q2` (cents, `ROUND_HALF_UP`).

## Edge Cases

- `medical_expenses_eur == 0` → deductible is 0.
- Medical expenses below zumutbare Belastung → deductible is 0.
- Bracket boundary: GdE exactly at 15,340 EUR or 51,130 EUR → next-tier rate applies only above the boundary (slab progression).
- married_separate: the joint deduction is allocated to person 1 by trace convention.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:zumutbare_belastung_2025`
- `tax_pipeline/y2025/germany_law.py:aussergewoehnliche_belastungen_deductible_2025`
- `tax_pipeline/y2025/germany_ordinary_rules.py:de25_aussergewoehnliche_belastungen`

## Test Coverage

- `tests/test_germany_aussergewoehnliche_belastungen_2025.py`

## Outputs Affected

- `de.ordinary.aussergewoehnliche_belastungen.deductible_eur` — deductible feeding DE25-07
- `de.ordinary.aussergewoehnliche_belastungen.zumutbare_belastung_eur` — slab burden for narrative
