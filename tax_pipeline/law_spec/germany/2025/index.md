# Germany 2025 Law Spec

This directory is the interpretation contract between German tax authorities and the `2025` Germany legal engine.

It is not the law itself. The law is the external authority. This directory records how this codebase interprets and operationalizes that law for the current implementation.

Use this layer to answer:

- what rule is being applied
- which inputs the code uses
- which ordering and rounding rules apply
- where a rule is implemented
- where it is tested
- which parts are still explicit filing positions rather than purely mechanical law

## Rules

- [assessment_ordering.md](assessment_ordering.md)
- [employment_income.md](employment_income.md)
- [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md)
- [retirement_contributions.md](retirement_contributions.md)
- [health_and_vorsorge.md](health_and_vorsorge.md)
- [basic_tariff.md](basic_tariff.md)
- [split_tariff.md](split_tariff.md)
- [ordinary_soli.md](ordinary_soli.md)
- [other_income_22nr3.md](other_income_22nr3.md)
- [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md)
- [equity_fund_teilfreistellung.md](equity_fund_teilfreistellung.md)
- [capital_tax_ordering.md](capital_tax_ordering.md)
- [treaty_dividend_credit.md](treaty_dividend_credit.md)
- [spouse_bank_capital_certificate.md](spouse_bank_capital_certificate.md)
- [private_sales_carryforwards.md](private_sales_carryforwards.md)
- [payments_and_crediting.md](payments_and_crediting.md)
- [final_refund_assembly.md](final_refund_assembly.md)
- [coverage.md](coverage.md)

## Manual-position-heavy areas

- treaty dividend credit amount from `outputs/tax-positions/de-model-assumptions.csv`
- factual work-use allocations for equipment and similar mixed-use items

## Main implementation files

- `tax_pipeline/y2025/germany_law.py`
- `tax_pipeline/y2025/germany_inputs.py`
- `tax_pipeline/pipelines/y2025/germany_model.py`

## Current Product Boundary

- `single` and `married_joint` are the supported Germany filing postures for the full `2025` pipeline.
- `married_separate` is only implemented through the ordinary-law layer today. The capital/output/forms/ELSTER surfaces intentionally fail loudly instead of generating a misleading combined household return.
- See the public support summary in [`docs/support-matrix.md`](../../../docs/support-matrix.md).
