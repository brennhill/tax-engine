# U.S. 2025 Exchange Rate And Wage Translation

## Authority

- IRS yearly average currency exchange rates
- Official URL:
  - https://www.irs.gov/individuals/international-taxpayers/yearly-average-currency-exchange-rates

## What This Rule Governs

The annual EUR-to-USD translation of foreign wages used in the current `2025` U.S. model.

## Inputs

- German wage facts in EUR
- IRS yearly average EUR/USD conversion rate

## Formula

`wages_usd = gross_wages_eur / eur_per_usd_yearly_average_2025`

## Ordering

This is the starting point for U.S. gross-income assembly.

## Rounding

- cents are preserved

## Edge Cases

- exchange rate must be positive

## Ambiguities / Filing Positions

The current model uses the IRS yearly average rate as its explicit translation posture.

## Implemented By

- `tax_pipeline/y2025/us_law.py:wages_usd_2025`
- `tax_pipeline/y2025/us_inputs.py:load_us_assessment_inputs_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `eur_per_usd_yearly_average_2025`
- `wages_usd`

