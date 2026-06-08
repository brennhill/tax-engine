# Germany 2025 Spouse Bank Capital Certificate

## Authority

- `§ 20 EStG`
- `§ 20 Abs. 9 EStG`
- `§ 32d EStG`
- `§ 36 Abs. 2 Nr. 2 EStG`
- `§ 36 Abs. 3 EStG`
- `§ 4 SolzG 1995`
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__20.html
  - https://www.gesetze-im-internet.de/estg/__32d.html
  - https://www.gesetze-im-internet.de/estg/__36.html
  - https://www.gesetze-im-internet.de/solzg_1995/__4.html

## What This Rule Governs

Typed domestic bank capital certificates in the Germany `2025` model.

## Inputs

- certificate owner slot
- certificate id and source file
- KAP line 7 capital income
- KAP line 8 stock-sale gains included in line 7
- KAP line 17 saver allowance used by the bank
- KAP line 37 withheld German capital tax
- KAP line 38 withheld solidarity surcharge
- KAP line 40 credited foreign tax
- KAP line 41 foreign tax not yet credited

## Formula

1. read typed bank certificate facts
2. validate non-negative amounts, known owner, unique certificate id, exact-one aliases for each typed field, and line 8 not exceeding line 7
3. split line 7 into the line 8 stock subset and the non-stock remainder
4. include the stock subset in the § 20 Abs. 6 stock bucket
5. include the non-stock remainder in the non-stock § 20 capital-income bucket
6. include line 40/41 foreign tax inside the § 32d Abs. 5 per-item credit cap
7. compute capital tax and capital solidarity surcharge under § 32d and SolzG
8. credit line 37/38 German withholding under § 36 only after the capital tax has been computed

## Ordering

This rule runs inside the capital assessment before final refund assembly. It intentionally prevents a post-hoc sidecar adjustment.

## Rounding

- certificate source facts are kept at cents
- § 32d capital tax and SolzG are rounded by the existing capital-tax helpers
- withholding credits are carried at cents into final refund assembly

## Edge Cases

- line 8 greater than line 7 fails closed
- duplicate certificate ids fail closed
- duplicate aliases for one typed certificate field fail closed
- unknown nonzero certificate keys fail closed
- a nonzero certificate for a missing owner slot fails closed
- zero certificate values produce no certificate object and no numerical effect

## Ambiguities / Filing Positions

The legal treatment is not safely mechanical as a sidecar. It interacts with joint saver allowance, § 20 loss netting, § 32d(5) foreign-tax caps, and § 36 withholding credits, so the model integrates it into the main capital package.

## Implemented By

- `tax_pipeline/pipelines/y2025/germany_model.py`
- `tax_pipeline/y2025/germany_law.py`

## Test Coverage

- `tests/test_germany_2025_law.py:test_bank_capital_certificate_integrates_into_joint_20_32d_36_sequence`
- `tests/test_germany_2025_law.py:test_bank_capital_certificate_line_8_cannot_exceed_line_7`
- `tests/test_germany_2025_law.py:test_legacy_spouse_bank_certificate_rows_load_as_typed_certificate`
- `tests/test_germany_2025_law.py:test_bank_certificate_loader_rejects_duplicate_aliases_for_same_typed_field`
- `tests/test_germany_2025_law.py:test_bank_certificate_loader_rejects_unknown_nonzero_certificate_facts`
- `tests/test_germany_2025_law.py:test_germany_model_final_result_integrates_bank_certificate_withholding_under_36`

## Outputs Affected

- `bank_certificate_*`
- `domestic_capital_*`
- final Germany refund/balance result
