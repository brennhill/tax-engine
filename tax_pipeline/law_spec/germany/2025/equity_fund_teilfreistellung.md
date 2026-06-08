# Germany 2025 Equity Fund Teilfreistellung

## Authority

- `InvStG § 20 Abs. 1`
- `InvStG § 20 Abs. 2`
- `InvStG § 20 Abs. 3`
- `InvStG § 21`
- `§ 32d Abs. 1 EStG`
- Official URLs:
  - https://www.gesetze-im-internet.de/invstg_2018/__20.html
  - https://www.gesetze-im-internet.de/invstg_2018/__21.html
  - https://www.gesetze-im-internet.de/estg/__32d.html

## What This Rule Governs

Teilfreistellung treatment for investment-fund income in the current `2025` Germany model.

## Inputs

- explicit fund classification by symbol
- fund income and gains
- taxable capital before Teilfreistellung

## Formula

1. require an explicit fund classification for every fund-like symbol
2. apply the InvStG § 20 private-investor Teilfreistellung rate by class:
   - Aktienfonds: `30%`
   - Mischfonds: `15%`
   - Immobilienfonds: `60%`
   - Auslands-Immobilienfonds: `80%`
   - sonstige Investmentfonds: `0%`
3. apply the same taxable percentage to fund losses under InvStG § 21 before netting them against other capital items
4. subtract the net Teilfreistellung adjustment from taxable capital before Teilfreistellung

## Ordering

This applies after capital bucket assembly and before the final capital-tax computation.

## Rounding

- cents are preserved

## Edge Cases

- taxable capital after Teilfreistellung cannot go below zero
- missing fund classification fails closed; the engine must not assume Aktienfonds treatment
- fund losses reduce taxable capital only by the taxable percentage that remains after the fund class's Teilfreistellung rate

## Ambiguities / Filing Positions

Fund classification can be a manual tax-position issue. The Teilfreistellung arithmetic is mechanical only after the fund class is explicit.

## Implemented By

- `tax_pipeline/pipelines/y2025/germany_model.py`

## Test Coverage

- `tests/test_germany_2025_law.py:test_unknown_fund_classification_fails_closed_under_invstg_20`
- `tests/test_germany_2025_law.py:test_fund_classification_applies_invstg_20_teilfreistellung_rates`
- `tests/test_germany_2025_law.py:test_fund_losses_are_reduced_by_teilfreistellung_under_invstg_21`

## Outputs Affected

- `equity_fund_total`
- `non_equity_fund_total`
- `fund_taxable_after_teilfreistellung`
- `teilfreistellung_reduction_base`
- `taxable_after_teilfreistellung`
