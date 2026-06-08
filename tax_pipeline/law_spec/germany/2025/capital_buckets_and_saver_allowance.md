# Germany 2025 Capital Buckets And Saver Allowance

## Authority

- `§ 20 EStG`
- `§ 20 Abs. 9 EStG`
- `§ 32d EStG`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__20.html
  - https://www.gesetze-im-internet.de/estg/__32d.html

## What This Rule Governs

The pre-tax capital bucket assembly in the current Germany `2025` model:

- stock gains
- fund gains
- fund Vorabpauschale rows supplied as income cashflows
- option gains
- positive cash income
- current-year § 20 loss netting
- restricted stock-loss carryforward use
- saver-allowance reduction before final capital tax

## Inputs

- capital sales detail
- income cashflows
- prior stock-loss carryforward
- saver allowance

## Formula

1. aggregate sales and income into the supported bucket categories
2. apply InvStG Teilfreistellung or partial loss disallowance to fund items
3. net current-year non-stock § 20 losses against positive capital income
4. consume the restricted prior stock-loss carryforward only against positive stock-sale gains remaining after current-year § 20 loss netting
5. add current-year stock-sale losses to the ending restricted stock-loss carryforward
6. combine the current-year capital buckets
7. for spouses assessed jointly, apply `§ 20 Abs. 9 Satz 3 EStG`: each spouse receives half of the `2,000 EUR` joint saver allowance first, and any unused half transfers to the other spouse
8. subtract the saver allowance to reach taxable capital before `§ 32d` tax
9. for foreign-tax-credit cap purposes, use each individual taxable foreign item/source before saver-allowance pro-rating; the aggregate credit is still capped against the remaining `§ 32d` tax

## Ordering

`Teilfreistellung -> § 20 loss netting -> Sparer-Pauschbetrag -> § 32d tax`

This is the capital-side base-building stage feeding the final flat-rate capital-tax ordering.

## Rounding

- cents are preserved

## Edge Cases

- stock-loss carryforward cannot exceed current stock gains
- current-year non-stock § 20 losses are netted before prior restricted stock-loss carryforward is consumed
- current-year stock-sale losses increase the ending stock-loss carryforward
- taxable capital cannot go below zero
- joint saver allowance cannot be assigned entirely to one spouse before testing the other spouse's half
- foreign-tax rows must include explicit refund-entitlement facts
- a foreign-tax row without a matching taxable foreign income item fails closed
- same-symbol foreign-tax fallback fails closed unless there is exactly one matching taxable item and one foreign-tax row

## Ambiguities / Filing Positions

Bucket classification is partly data-model-driven. Fund classification questions live in the equity-fund and treaty-position layers, not here.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:compute_germany_capital_assessment_2025`
- `tax_pipeline/pipelines/y2025/germany_model.py:compute_capital_buckets` parses normalized CSV rows into typed law-core facts only

## Test Coverage

- `tests/test_germany_2025_law.py:test_capital_assessment_exposes_law_ordered_core_stages`
- `tests/test_germany_2025_law.py:test_spouse_bank_certificate_uses_remaining_allowance_after_teilfreistellung`
- `tests/test_germany_2025_law.py:test_capital_foreign_tax_credit_cap_uses_foreign_item_not_same_symbol_sale_gain`
- `tests/test_germany_2025_law.py:test_stock_loss_carryforward_waits_until_current_year_other_capital_losses_are_net_under_20_6`
- `tests/test_germany_2025_law.py:test_capital_foreign_tax_fallback_symbol_must_be_unambiguous_under_32d5`

## Outputs Affected

- `dher_stock_gain`
- `stock_gain`
- `stock_loss_carryforward_2024`
- `stock_loss_carryforward_used`
- `stock_gain_after_carryforward`
- `fund_gain`
- `option_gain`
- `positive_income_total`
- `combined_current_capital`
- `saver_allowance`
- `taxable_before_teilfreistellung`
