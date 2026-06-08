# U.S. 2025 Law Spec

This directory is the interpretation contract between U.S. tax authorities and the `2025` U.S. legal engine.

It is not the law itself. The law is the external authority. This directory records how this codebase interprets and operationalizes that law for the current implementation.

Use this layer to answer:

- what rule is being applied
- which inputs the code uses
- which ordering and rounding rules apply
- where a rule is implemented
- where it is tested
- which parts are still explicit filing positions rather than purely mechanical law

## Rules

- [exchange_rate_and_wage_translation.md](exchange_rate_and_wage_translation.md)
- [capital_gain_netting.md](capital_gain_netting.md)
- [agi_and_taxable_income.md](agi_and_taxable_income.md)
- [regular_tax.md](regular_tax.md)
- [qualified_dividend_worksheet.md](qualified_dividend_worksheet.md)
- [capital_loss_limit.md](capital_loss_limit.md)
- [ftc_limitation.md](ftc_limitation.md)
- [allowed_ftc.md](allowed_ftc.md)
- [niit.md](niit.md)
- [amt.md](amt.md)
- [treaty_resourcing.md](treaty_resourcing.md)
- [payments_and_refund.md](payments_and_refund.md)
- [coverage.md](coverage.md)

## Manual-position-heavy areas

- general-category foreign tax allocation by wage share
- positive-income-only FTC denominator posture
- German residual-tax cap used in the treaty re-sourcing worksheet
- treaty dividend source split assumptions

## Main implementation files

- `tax_pipeline/y2025/us_law.py`
- `tax_pipeline/y2025/us_inputs.py`
- `tax_pipeline/pipelines/y2025/us_model.py`

## Current Product Boundary

- `single`, `mfs_nra_spouse`, and `married_joint` are the supported U.S. filing postures in the current `2025` engine.
- Other filing statuses are not implemented yet.
- Several FTC and treaty outcomes still rely on explicit filing-position inputs rather than fully automatic law-only inference.
- See the public support summary in [`docs/support-matrix.md`](../../../docs/support-matrix.md).
