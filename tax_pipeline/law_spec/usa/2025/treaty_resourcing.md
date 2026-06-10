# U.S. 2025 Treaty Re-Sourcing

## Authority

- Germany treaty technical explanation
- IRS Publication `514`
- Official URLs:
  - https://www.irs.gov/pub/irs-trty/germtech.pdf
  - https://www.irs.gov/publications/p514

## What This Rule Governs

The current codebase's treatment of treaty re-sourcing on certain U.S.-source dividends in the `2025` U.S. model.

## Inputs

- computed U.S.-source dividends
- computed U.S.-source qualified dividends
- the current regular-tax result
- explicit U.S.-source dividend split assumptions
- Germany's typed same-run treaty packet for gross dividend base, Article 10 source-tax ceiling, pre-credit German tax, and allowed German credit on the same U.S.-source dividend stack

## Formula

The implemented logic follows the current saved worksheet posture:

<!-- IRS-VERIFIED 2026-06-10: Pub. 514 "Tax Treaties" worksheet line numbers 16/17/18/19/20c/21 and the Form 1040 line 15 (taxable income) / line 16 (tax) references below are verified against https://www.irs.gov/publications/p514 and the 2025 Form 1040 (https://www.irs.gov/pub/irs-pdf/f1040.pdf). Line 16 average rate = tax ÷ taxable income (line 15), NOT AGI (the F-FN-2 fix). -->
1. isolate the U.S.-source dividend stack
2. compute the Publication 514 worksheet line 16 estimated U.S. tax by dividing Form 1040 line 16 tax by **taxable income (Form 1040 line 15)** — NOT AGI (the F-FN-2 fix; AGI as the divisor understates the average rate) — and multiplying that average rate by net U.S.-source income in the category
3. compute the treaty minimum source-country tax (worksheet line 17 = 15 % of gross under DBA-USA Art. 10(2)(b))
4. compute the excess U.S. tax above the treaty floor (worksheet line 18 = max of 0 and line 16 minus line 17)
5. validate that Germany's treaty-dividend gross matches the U.S.-computed U.S.-source dividend stack
6. feed Germany's computed dividend-stage residence credit into the worksheet line 19 greater-of clamp and Germany's computed dividend-stage pre-credit tax into the line 20c clamp
7. cap the additional credit by the residence-country residual-tax worksheet result (line 21 = lesser of line 19 and line 20c)
<!-- IRS-VERIFIED 2026-06-10: worksheet lines 17/18/19/20c/21 above verified against IRS Pub. 514 "Tax Treaties" additional-foreign-tax-credit worksheet (https://www.irs.gov/publications/p514). -->

## Ordering

This applies only when the treaty re-sourcing election is enabled and after regular tax and baseline FTCs are known.

Publication 514 line 21 is modeled as an additional credit shown outside the baseline Form 1116 category limitation:

- add line 21 to Form 1116 Part III line 12 before completing Form 1116
- also add line 21 to Form 1116 Part IV line 32 and Schedule 3 line 1

## Rounding

- cents are preserved

## Edge Cases

- no treaty re-sourcing if the election is disabled
- no treaty re-sourcing if the computed U.S.-source dividends are negative or inconsistent
- treaty re-sourcing with positive U.S.-source dividends fails closed unless the same pipeline run supplies Germany core outputs for all matched dividend stack fields
- manual dividend split must reconcile to computed U.S.-source dividends
- stale or edited audit packet files must not affect the U.S. calculation

## Ambiguities / Filing Positions

This rule is mechanical once treaty re-sourcing is selected.

The U.S. model consumes Germany's typed same-run packet in memory, not ad hoc fields from `germany-model-results.json` and not a durable bridge file.

The packet contains item IDs, Article 10 source-tax ceiling, German pre-credit tax, and German residence-country credit. The U.S. loader requires the Germany item IDs to match `us-treaty-dividend-items.csv` and records the EUR/USD reconciliation as audit text. Amount coverage is therefore by item identity first, not by reverse-converting Germany EUR gross dividends and hoping the USD total happens to match. `de-us-treaty-dividend-packet.md` may be written after Germany runs, but it is audit-only and is not read by the U.S. legal core.

It still depends on explicit filing positions for:

- whether treaty re-sourcing is claimed
- the U.S.-source dividend split by category

So the arithmetic is deterministic, and the cross-country dividend coverage is verified before any additional treaty FTC is computed.

## Implemented By

- `tax_pipeline/y2025/us_law.py:validate_treaty_resourcing_dividend_split_2025`
- `tax_pipeline/y2025/us_law.py:validate_germany_treaty_dividend_coverage_2025`
- `tax_pipeline/y2025/us_law.py:validate_treaty_resourcing_inputs_2025`
- `tax_pipeline/y2025/us_law.py:treaty_resourcing_assessment_2025`

## Test Coverage

- `tests/test_us_2025_law.py`
- `tests/test_us_2025_law.py:test_treaty_resourcing_uses_explicit_germany_dividend_credit_outputs`
- `tests/test_us_2025_law.py:test_treaty_resourcing_requires_germany_core_outputs_for_us_source_dividends`
- `tests/test_us_2025_law.py:test_treaty_resourcing_requires_germany_dividend_base_to_match_us_source_stack`
- `tests/test_us_2025_law.py:test_treaty_resourcing_requires_us_and_germany_item_coverage_to_match`
- `tests/test_us_2025_law.py:test_foreign_source_qualified_dividends_must_be_subset_of_foreign_passive_dividends`
- `tests/test_us_2025_law.py:test_load_us_assessment_inputs_uses_germany_treaty_packet_when_present`
- `tests/test_us_2025_law.py:test_load_us_assessment_inputs_rejects_explicit_germany_packet_coverage_gap`
- `tests/test_us_2025_law.py:test_load_us_assessment_inputs_ignores_stale_audit_only_germany_treaty_packet`
- `tests/test_us_2025_law.py:test_load_us_assessment_inputs_preserves_zero_germany_treaty_dividend_outputs`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-estimate.json treaty_resourcing.*`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv treaty_resourcing_*`
- `years/<year>/outputs/analysis-steps/us-treaty-resourcing-worksheet.csv`
