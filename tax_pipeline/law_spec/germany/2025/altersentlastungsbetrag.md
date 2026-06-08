# Germany 2025 § 24a EStG Altersentlastungsbetrag

## Authority

- `§ 24a EStG`
- Official URL: https://www.gesetze-im-internet.de/estg/__24a.html

## What This Rule Governs

The age-relief allowance for taxpayers who have completed their 64th year of life **before** the start of the assessment year. The allowance applies to ordinary income (Einkünfte) other than § 19 wages and certain Versorgungsbezüge; capital income is excluded unless the taxpayer elects Günstigerprüfung under § 32d Abs. 6 EStG.

The percentage rate and Euro cap are fixed for life by the calendar year in which the taxpayer first met the 64-year threshold (§ 24a Satz 5 EStG and the Anlage to § 24a EStG).

## Inputs

- `de.ordinary.people` — per-person `birth_year` (zero means "not declared")
- `de.ordinary.other_income_22nr3_taxable` — eligible-base proxy (the implementation conservatively excludes § 19 employment income)
- `de.constants.altersentlastungsbetrag_tax_year` — the assessment year used for the age-threshold check (2025)

## Formula

For each person:

- if `birth_year + 64 >= tax_year` the allowance is `0` (the taxpayer has not completed the 64th year before the start of the assessment year);
- otherwise: `min(cap, rate × eligible_income)` where `(rate, cap)` is the row in `ALTERSENTLASTUNGSBETRAG_2025_TABLE` keyed by `birth_year + 64`. For taxpayers who turned 64 before 2005, the 2005 row applies.

The household total is the sum of per-person amounts.

## Ordering

`§ 24a Satz 1 EStG` reduces the Gesamtbetrag der Einkünfte before the Sonderausgabenabzug, so the stage runs after `DE25-04-OTHER-22NR3` and before `DE25-05-RETIREMENT-SA`. `DE25-07-TAXABLE-INCOME` subtracts the allowance before § 26b joint aggregation / § 2 Abs. 5 zvE assembly.

## Rounding

- `q2` (cents, `ROUND_HALF_UP`) per person.

## Edge Cases

- `birth_year == 0` (not declared) → allowance is `0`.
- Taxpayer turns 64 during the assessment year → allowance is `0` (Satz 3 / Satz 5 require the 64th year to be completed before the start of the assessment year).
- Married joint: applied independently per spouse and summed (each spouse carries their own cohort).

## Implemented By

- `tax_pipeline/y2025/germany_law.py:altersentlastungsbetrag_2025`
- `tax_pipeline/y2025/germany_ordinary_rules.py:de25_altersentlastungsbetrag`

## Test Coverage

- `tests/test_germany_altersentlastungsbetrag_2025.py`

## Outputs Affected

- `de.ordinary.altersentlastungsbetrag.total_eur` — household allowance feeding DE25-07
- `de.ordinary.altersentlastungsbetrag.by_person` — per-person breakdown for narrative trace
