# Germany 2025 U.S. Treaty Dividend Credit

## Authority

- Germany-U.S. treaty Articles `10` and `23`
- `§ 32d Abs. 5 EStG`
- Official URLs:
  - https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html?gtp=249348_list%253D2
  - https://www.gesetze-im-internet.de/estg/__32d.html

## What This Rule Governs

The Germany-side credit for supported U.S.-source portfolio dividends received by a German-resident U.S. citizen.

This rule is dividend-specific. It does not apply to stock-sale gains, ETF sale gains, short-term gains, long-term gains, interest, royalties, or unsupported special dividend classes.

## Inputs

- `outputs/tax-positions/de-us-treaty-dividend-items.csv`
- matching taxable dividend rows in `normalized/derived-facts/germany/income-cashflows.csv`
- `gross_dividend_eur`
- `german_taxable_dividend_eur`
- `treaty_rate`

## Formula

For each supported U.S.-source portfolio dividend item:

1. Match the treaty item to a taxable German § 20/InvStG dividend item by `foreign_tax_item_id`.
2. Compute the Article 10 source-country ceiling from treaty law: `gross_dividend_eur * 15%`.
3. Feed the treaty-allowed U.S. source tax into the same § 32d Abs. 5 foreign-tax-credit path as other item/source-capped foreign tax.
4. Apply the § 20 Abs. 9 Sparer-Pauschbetrag before exporting treaty worksheet values.
5. Export German pre-credit tax on the same dividend only after the allowance allocation: `post_allowance_taxable_dividend_eur * 25%`.
6. Export the Germany-side treaty dividend credit only after the actual § 32d Abs. 5 credit cap is known.
7. Emit a typed same-run packet in memory for the U.S. model, and write `de-us-treaty-dividend-packet.md` only as an audit artifact. The U.S. model must not read this durable audit file as a logic input.

## Ordering

This is applied inside the § 32d Abs. 5 EStG credit stage, after § 20 Abs. 9 EStG allowance ordering and before the remaining capital income tax is used for SolzG.

The legacy scalar `treaty_dividend_credit_eur` is still rejected when nonzero because a separate post-§32d treaty subtraction would double-count the same relief.

## Rounding

- cents are preserved

## Edge Cases

- treaty item without a matching taxable dividend fails closed
- unsupported dividend class fails closed
- treaty rate other than the implemented 15% portfolio-dividend rate fails closed
- stock gains cannot enter this path
- a dividend fully sheltered by Sparer-Pauschbetrag exports `0.00` German pre-credit tax and `0.00` Germany-side credit for U.S. Pub. 514 lines 17/18
- a stale or edited audit artifact cannot affect the U.S. calculation because the U.S. pipeline consumes only the typed same-run packet

## Ambiguities / Filing Positions

The legacy `allocated_us_tax_paid_eur` sidecar field is retained only as an input compatibility field. It does not reduce the Article 10 treaty amount; any future filing posture that uses actual paid U.S. tax instead of the treaty ceiling must be modeled as an explicit law branch.

Fund and REIT dividend classes remain explicit because the German taxable base can differ from the gross dividend.

## Implemented By

- `tax_pipeline/y2025/germany_law.py:GermanyTreatyDividendItem2025`
- `tax_pipeline/y2025/germany_law.py:treaty_relieved_capital_tax_2025`
- `tax_pipeline/y2025/germany_law.py:compute_germany_capital_assessment_2025`
- `tax_pipeline/pipelines/y2025/germany_model.py`

## Test Coverage

- `tests/test_germany_2025_law.py:test_us_treaty_dividend_credit_is_integrated_through_32d5`
- `tests/test_germany_2025_law.py:test_us_treaty_dividend_article_10_amount_is_derived_from_gross_and_rate`
- `tests/test_germany_2025_law.py:test_us_treaty_dividend_export_uses_post_allowance_actual_32d5_result`
- `tests/test_germany_2025_law.py:test_us_treaty_dividend_item_requires_matching_taxable_dividend`
- `tests/test_germany_2025_law.py:test_us_treaty_dividend_item_rejects_stock_gain_classification`
- `tests/test_germany_2025_law.py:test_de_us_treaty_dividend_items_load_as_typed_article_10_facts`

## Outputs Affected

- `treaty_us_source_dividend_gross_eur`
- `treaty_us_source_dividend_precredit_tax_eur`
- `treaty_us_source_dividend_allowed_us_tax_eur`
- `treaty_us_source_dividend_credit_eur`
- `treaty_dividend_credit`
- `capital_soli_with_teilfreistellung_after_treaty`
- `capital_income_tax_with_teilfreistellung_after_treaty`
- `capital_tax_with_teilfreistellung_after_treaty`
