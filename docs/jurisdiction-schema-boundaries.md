# Jurisdiction Schema Boundaries

This repo should share only tax-neutral facts across countries.

The safe boundary is:

- `source facts`
  Document-native facts that mirror what the source literally says.
- `shared derived facts`
  Economic facts that are still jurisdiction-neutral.
- `jurisdiction-specific derived facts`
  Country-shaped derived facts used only by one tax system.
- `tax positions`
  Legal conclusions, line mappings, credits, deductions, and filing outputs.

## Rule

If a field name depends on tax-law wording, it must not be shared across jurisdictions.

Good shared facts:

- `worked_from_home_days`
- `workspace_exclusive_use`
- `workspace_area_sqm`
- `capital_sale_proceeds`
- `foreign_tax_withheld`
- `gross_wage`

Bad shared names:

- `home_office_deduction`
- `home_office_eligible`
- `foreign_tax_credit`
- `qualified_for_aktienfonds`

## Example: Home Office

Germany and the U.S. both have home-office concepts, but they are not the same legal rule.

- Germany can allow a work-from-home day-based deduction without requiring dedicated office space.
- The U.S. home-office rule generally requires exclusive-use dedicated space.

So the shared layer can store facts such as:

- `worked_from_home_days`
- `workspace_exclusive_use`
- `workspace_primary_place_of_business`

But it must not define one cross-country legal field like:

- `home_office_deduction`
- `home_office_allowed`

## Where Jurisdiction-Specific Names Belong

- `years/<year>/config/`
  Human-maintained jurisdiction-specific inputs and elections.
- `years/<year>/normalized/derived-facts/`
  Jurisdiction-specific derived facts when the transformation is already country-shaped.
- `years/<year>/outputs/tax-positions/`
  Explicit legal positions, assumptions, line mappings, and filing outputs.

## Current Flagged Names

These names are currently acceptable only because they already live in jurisdiction-specific
config or tax-position layers. They must not be promoted into a shared fact schema.

| Current name | Current location | Why it is law-loaded | Safer shared alternative |
| --- | --- | --- | --- |
| `home_office_days_without_first_workplace_visit` | `years/<year>/config/manual_overrides.json` | Germany `Tagespauschale` concept | `worked_from_home_days` |
| `home_office_days_with_first_workplace_visit` | `years/<year>/config/manual_overrides.json` | Germany-specific commuting/workplace distinction | `worked_from_home_days` plus separate visit facts |
| `telecom_deduction_eur` | `years/<year>/config/manual_overrides.json` | Legal deduction label, not a raw fact | `telecom_cost_eur`, `telecom_business_use_share` |
| `employment_legal_insurance_deduction_eur` | `years/<year>/config/manual_overrides.json` | Legal deduction label | `employment_legal_insurance_cost_eur` |
| `cross_border_tax_help_deduction_eur` | `years/<year>/config/manual_overrides.json` | Deduction/legal treatment embedded in name | `cross_border_tax_help_fee_eur` |
| `health_insurance_sick_pay_reduction_rate` | `years/<year>/config/manual_overrides.json` | Germany `§ 10` deduction treatment | `statutory_health_nonbasic_share_rate` if shared at all |
| `ftc_denominator_positive_income_only` | `years/<year>/outputs/tax-positions/us-model-assumptions.csv` | U.S. FTC filing posture | none; keep in U.S. tax positions |
| `allocate_joint_german_tax_by_wage_share` | `years/<year>/outputs/tax-positions/us-model-assumptions.csv` | U.S. FTC allocation posture | none; keep in U.S. tax positions |
| `us_source_direct_equity_dividends_usd` | `years/<year>/outputs/tax-positions/us-model-assumptions.csv` | U.S. treaty worksheet category | `ordinary_dividends_usd` only at shared level |
| `us_source_equity_fund_dividends_usd` | `years/<year>/outputs/tax-positions/us-model-assumptions.csv` | U.S. treaty worksheet category | `ordinary_dividends_usd` only at shared level |
| `us_source_non_equity_fund_dividends_usd` | `years/<year>/outputs/tax-positions/us-model-assumptions.csv` | U.S. treaty worksheet category | `ordinary_dividends_usd` only at shared level |
| `de-us-treaty-dividend-packet.md` | `years/<year>/outputs/analysis-steps/` | Audit-only Germany-to-U.S. treaty packet report | none; generated from Germany legal core after the in-memory same-run packet is emitted |

## Resolved Naming Fixes

The current repo now uses these cleaner locations:

| Old shape | New shape | Reason |
| --- | --- | --- |
| `normalized/derived-facts/us-other-income-derived-facts.csv` | `normalized/derived-facts/common/other-income-facts.csv` | shared tax-neutral economic facts |
| `normalized/facts/us-german-wage-source-facts.csv` | `normalized/derived-facts/usa/foreign-wage-support.csv` | U.S.-specific FTC support belongs in U.S. derived facts |
| `normalized/facts/us-income-source-facts.csv` | `normalized/derived-facts/usa/income-summary.csv` | U.S.-specific income rollup belongs in U.S. derived facts |
| flat Germany derived-fact files in `normalized/derived-facts/` | `normalized/derived-facts/germany/...` | Germany-shaped derived facts stay under Germany |
| flat U.S. derived-fact files in `normalized/derived-facts/` | `normalized/derived-facts/usa/...` | U.S.-shaped derived facts stay under USA |

## Remaining Smells To Avoid

These are not necessarily wrong today, but they should not be copied into future shared schema.

| Current artifact | Current issue | Better shape |
| --- | --- | --- |
| `telecom_deduction_eur` in config | legal treatment embedded in the name | split cost from deductible treatment if the shared layer ever needs it |

## Working Rule For New Fields

Before adding a field, ask:

1. Does this describe the source document literally?
2. Does this describe economic reality without legal interpretation?
3. Or does this already assume one country’s tax rule?

Use:

- `source facts` for `1`
- shared facts / shared derived facts for `2`
- country-specific config, derived facts, or tax positions for `3`
