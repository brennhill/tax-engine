# Germany 2025 § 33a EStG Unterhaltsleistungen

## Authority

- `§ 33a Abs. 1 EStG`
- Official URL: https://www.gesetze-im-internet.de/estg/__33a.html

## What This Rule Governs

Deduction of support payments to a legally entitled person (estranged or divorced spouse — see § 1361 / § 1569 BGB; parents — § 1601 BGB; child without Kindergeld). The cap equals the 2025 Grundfreibetrag (€12,096) and is reduced by the recipient's own income/maintenance above €624 ("Eigenbezüge").

## Inputs

- `de.ordinary.raw_inputs.support_payments_eur`
- `de.ordinary.raw_inputs.support_recipient_income_eur`
- `de.ordinary.raw_inputs.support_recipient_relationship` ∈ `{estranged_spouse, divorced_spouse, parent, child_no_kindergeld}`
- `de.constants.unterhaltsleistungen_grundfreibetrag` (Grundfreibetrag, € 12,096 for 2025)

## Formula

```
eigenbezuege_reduction = max(0, recipient_income_eur - 624)
cap = max(0, grundfreibetrag_eur - eigenbezuege_reduction)
deductible = min(support_payments_eur, cap)
```

## Ordering

The deduction is applied in DE25-07 against zvE, in parallel with the § 33 außergewöhnliche-Belastungen deduction. § 33a Abs. 4 EStG forbids combining the same expense in both stages; a future enhancement may add an explicit cross-stage gate.

## Rounding

- `q2` (cents, `ROUND_HALF_UP`).

## Edge Cases

- `support_payments_eur == 0` and no relationship → deductible is 0 (no error).
- `support_payments_eur > 0` with empty/invalid relationship → fail closed with `ValueError`.
- Recipient income ≤ 624 EUR → cap is the full Grundfreibetrag.
- Recipient income high enough that the reduction zeroes the cap → deductible is 0.
- `married_separate`: deduction is allocated to person 1 by trace convention.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:unterhaltsleistungen_deductible_2025`
- `tax_pipeline/y2025/germany_ordinary_rules.py:de25_unterhaltsleistungen`

## Test Coverage

- `tests/test_germany_unterhaltsleistungen_2025.py`

## Outputs Affected

- `de.ordinary.unterhaltsleistungen.deductible_eur` — feeds DE25-07
