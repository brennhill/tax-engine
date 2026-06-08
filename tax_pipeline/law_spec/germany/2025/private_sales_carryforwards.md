# Germany 2025 Private Sales And Carryforwards

## Authority

- `§ 23 EStG`
- Official URL:
  - https://www.gesetze-im-internet.de/estg/__23.html

## What This Rule Governs

The private-sale carryforward treatment currently shown in the Germany model, including the Coinbase crypto `§ 23` result.

## Inputs

- prior private-sale carryforward
- documented `2025` private-sale gains/losses

## Formula

- use prior carryforward against documented current-year `§ 23` gains
- unused carryforward remains
- additional current-year private-sale loss increases the carryforward

## Ordering

This is separate from the main ordinary-income and capital-income tax path.

## Rounding

- cents are preserved

## Edge Cases

- no current-year gains
- current-year loss increasing the carryforward

## Ambiguities / Filing Positions

The arithmetic is mechanical once the `§ 23` result is fixed. The underlying factual classification of crypto events into `§ 23` is handled in the separate Coinbase pipeline.

## Implemented By

- `tax_pipeline/pipelines/y2025/coinbase_private_sales.py`
- `tax_pipeline/pipelines/y2025/germany_model.py`

## Test Coverage

- covered indirectly by the locked `2025` regression

## Outputs Affected

- `private_sale_loss_carryforward_2024`
- `private_sale_gains_2025`
- `private_sale_loss_used`
- `private_sale_loss_remaining`
- `coinbase_private_sale_result_2025`
- `coinbase_private_sale_carryforward_after_2025`

