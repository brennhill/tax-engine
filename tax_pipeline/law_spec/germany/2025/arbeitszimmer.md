# Germany 2025 § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer

## Authority

- `§ 4 Abs. 5 Satz 1 Nr. 6b EStG`
- `§ 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG` (mutual exclusion with Tagespauschale)
- Official URL: https://www.gesetze-im-internet.de/estg/__4.html

## What This Rule Governs

Deduction for a household work room (Arbeitszimmer):

- If the home office is the *Mittelpunkt der gesamten betrieblichen und beruflichen Betätigung* (§ 4 Abs. 5 Satz 1 Nr. 6b Satz 2 EStG), the **actual costs** are deductible.
- Otherwise, the **Jahrespauschale of €1,260** applies (§ 4 Abs. 5 Satz 1 Nr. 6b Satz 4 EStG).
- § 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG forbids combining the Nr. 6b Pauschale with the Nr. 6c Tagespauschale (modeled in DE25-02 Werbungskosten) for the same period.

## Inputs

- `de.ordinary.raw_inputs.arbeitszimmer_claimed`
- `de.ordinary.raw_inputs.arbeitszimmer_qualifies_as_mittelpunkt`
- `de.ordinary.raw_inputs.arbeitszimmer_actual_costs_eur`
- `de.ordinary.people` (per-person `home_office_days_*` for the mutual-exclusion check)

## Formula

```
if not arbeitszimmer_claimed:
    return 0
if tagespauschale_days_total > 0:
    raise ValueError(...)  # § 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG
if qualifies_as_mittelpunkt:
    return actual_costs_eur
return ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR  # 1,260
```

## Ordering

The deduction is parallel to DE25-02 Werbungskosten and runs after DE25-ALTERSENTLASTUNGSBETRAG. DE25-07 subtracts the Arbeitszimmer amount before zvE assembly.

## Rounding

- `q2` (cents, `ROUND_HALF_UP`).

## Edge Cases

- `arbeitszimmer_claimed == False` → 0 (no Pauschale by default).
- Both Tagespauschale and Arbeitszimmer claimed → fail closed with election guidance.
- Mittelpunkt + actual_costs_eur=0 → deductible 0 (genuine zero-cost case).

## Implemented By

- `tax_pipeline/y2025/germany_law.py:arbeitszimmer_deductible_2025`
- `tax_pipeline/y2025/germany_ordinary_rules.py:de25_arbeitszimmer`

## Test Coverage

- `tests/test_germany_arbeitszimmer_2025.py`

## Outputs Affected

- `de.ordinary.arbeitszimmer.deductible_eur` — feeds DE25-07
