# Germany 2025 § 33b EStG Behinderten-Pauschbetrag

## Authority

- `§ 33b Abs. 3 EStG`, `§ 33b Abs. 7 EStG`
- Official URL: https://www.gesetze-im-internet.de/estg/__33b.html
- Behinderten-Pauschbetragsgesetz (BGBl. I 2020 S. 2770) — doubled the rates effective 2021.

## What This Rule Governs

Per-person flat allowance for taxpayers with a recognized Grad der Behinderung (GdB) ≥ 20, or the special amount for hilflose/blinde Menschen.

## Inputs

- `de.ordinary.people` — per-person `gdb` (multiple of 10, 0 = not declared) and `hilflos_or_blind` flag

## Schedule (2025)

| GdB tier | Pauschbetrag |
| --- | --- |
| 20 | 384 EUR |
| 30 | 620 EUR |
| 40 | 860 EUR |
| 50 | 1 140 EUR |
| 60 | 1 440 EUR |
| 70 | 1 780 EUR |
| 80 | 2 120 EUR |
| 90 | 2 460 EUR |
| 100 | 2 840 EUR |
| Hilflos / blind (special) | 7 400 EUR |

## Formula

```python
if hilflos_or_blind:
    return 7400
if gdb <= 0:
    return 0
if gdb % 10 != 0 or gdb < 20 or gdb > 100:
    raise ValueError(...)
return BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[gdb]
```

## Ordering

Per-person allowance subtracted at DE25-07 from each person's zvE bucket (married_separate / single) or summed into the joint household reduction (married_joint).

§ 33b Abs. 7 EStG forbids stacking the same disability-related expense in § 33; the cross-stage gate is a future enhancement.

## Rounding

- `q2` (cents, `ROUND_HALF_UP`).

## Edge Cases

- `gdb == 0` and `hilflos_or_blind == False` → allowance is 0.
- Invalid GdB (not a multiple of 10, or outside [20, 100]) → fail closed with `ValueError`.
- `hilflos_or_blind == True` overrides the GdB schedule (the special amount supersedes the tier).
- Married joint with both spouses claiming → both per-person allowances are summed.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:behinderung_pauschbetrag_2025`
- `tax_pipeline/y2025/germany_ordinary_rules.py:de25_behinderung_pauschbetrag`

## Test Coverage

- `tests/test_germany_behinderung_pauschbetrag_2025.py`

## Outputs Affected

- `de.ordinary.behinderung_pauschbetrag.total_eur` — feeds DE25-07
- `de.ordinary.behinderung_pauschbetrag.by_person` — per-person breakdown for narrative
