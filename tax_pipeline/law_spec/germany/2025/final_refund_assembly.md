# Germany 2025 Final Refund Assembly

## Authority

- `§ 36 Abs. 2 EStG`
- `§ 32d EStG`
- `InvStG § 20`
- `§ 22 Nr. 3 EStG`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__36.html
  - https://www.gesetze-im-internet.de/estg/__32d.html
  - https://www.gesetze-im-internet.de/invstg_2018/__20.html
  - https://www.gesetze-im-internet.de/estg/__22.html

## What This Rule Governs

The final assembly of the modeled Germany refund after combining:

- ordinary assessment
- capital tax
- treaty-position effect
- domestic bank certificate withholding credits

Domestic bank certificate facts are integrated in the joint capital sequence before final assembly. Their KEST and solidarity-surcharge withholding credits are applied under `§ 36 Abs. 2 Nr. 2 EStG` only after the `§ 20`/`§ 32d` capital tax has been computed.

## Inputs

- `ordinary_refund_before_capital_eur`
- capital tax before and after treaty
- domestic bank certificate KEST/soli withholding credits

## Formula

1. subtract capital tax before treaty from the ordinary refund base to get the pre-treaty result
2. subtract capital tax after treaty from the ordinary refund base to get the post-treaty result
3. add domestic bank certificate withholding credits
4. use that post-withholding result as the final target refund

## Ordering

This is the last Germany assembly stage.

## Rounding

- cents are preserved

## Edge Cases

- refund can become additional balance due if the capital side exceeds ordinary credits
- nonzero bank certificate facts must be integrated into the capital core before final assembly; renderers must not add them as a post-hoc sidecar

## Ambiguities / Filing Positions

The assembly arithmetic is mechanical. Treaty and some factual inputs inside it can still depend on explicit positions handled in other rule files.

## Implemented By

- `tax_pipeline/pipelines/y2025/germany_model.py`

## Test Coverage

- covered indirectly by the locked `2025` regression

## Outputs Affected

- `refund_before_treaty`
- `chosen_refund_before_domestic_certificate`
- `domestic_capital_withholding_credit`
- `final_target_refund`
