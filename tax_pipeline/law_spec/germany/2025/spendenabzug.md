# Germany 2025 § 10b EStG Spendenabzug

## Authority

- `§ 10b Abs. 1 EStG`
- Official URL: https://www.gesetze-im-internet.de/estg/__10b.html

## What This Rule Governs

Sonderausgaben deduction for charitable donations / membership dues to recognized organizations. The deduction is capped at 20 % of the Gesamtbetrag der Einkünfte (GdE).

## Out of Scope

- § 10b Abs. 1 Satz 1 Nr. 2 EStG: alternative entrepreneur cap (4 ‰ of revenue + wage sum).
- § 10b Abs. 1 Sätze 9-10 EStG: carryforwards (Großspendenrest). Non-zero carryforwards fail closed.

## Inputs

- `de.ordinary.raw_inputs.charitable_donations_eur`
- `de.ordinary.raw_inputs.charitable_donations_carryforward_eur` (must be 0)
- `de.ordinary.net_employment_income`, `de.ordinary.other_income_22nr3_taxable`,
  `de.ordinary.altersentlastungsbetrag` (the GdE base)

## Formula

```
GdE = sum(net_employment) + § 22 Nr. 3 taxable - § 24a allowance
cap = 0.20 * GdE
deductible = min(donations, cap)
```

## Ordering

§ 10b is a Sonderausgabe; the implementation places it after DE25-06B (Sonderausgaben-Pauschbetrag) and before DE25-07 zvE assembly. The 20 % cap uses the GdE *after* § 24a Altersentlastungsbetrag (§ 2 Abs. 4 EStG).

## Rounding

- `q2` (cents, `ROUND_HALF_UP`).

## Edge Cases

- `charitable_donations_eur == 0` → deductible 0.
- Donations under cap → deductible equals donations.
- Donations above cap → deductible truncates to `0.20 × GdE`.
- `charitable_donations_carryforward_eur > 0` → fail closed (`NotImplementedError`).

## Implemented By

- `tax_pipeline/y2025/germany_law.py:spendenabzug_2025`
- `tax_pipeline/y2025/germany_ordinary_rules.py:de25_spendenabzug`

## Test Coverage

- `tests/test_germany_spendenabzug_2025.py`

## Outputs Affected

- `de.ordinary.spendenabzug.deductible_eur` — feeds DE25-07
