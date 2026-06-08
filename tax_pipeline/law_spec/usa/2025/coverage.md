# U.S. 2025 Law Spec Coverage

This file maps canonical U.S. trace steps to law-spec files.

Every step in `years/<year>/outputs/analysis-steps/us-tax-trace.csv` should match at least one pattern below.

| Pattern | Rule Spec | Notes |
| --- | --- | --- |
| `eur_per_usd_yearly_average_2025` | [exchange_rate_and_wage_translation.md](exchange_rate_and_wage_translation.md) | FX source |
| `wages_usd` | [exchange_rate_and_wage_translation.md](exchange_rate_and_wage_translation.md) | Wage translation |
| `capital_gain_or_loss_line_7a` | [capital_gain_netting.md](capital_gain_netting.md) | Final capital line 7a |
| `adjusted_gross_income` | [agi_and_taxable_income.md](agi_and_taxable_income.md) | AGI |
| `taxable_income` | [agi_and_taxable_income.md](agi_and_taxable_income.md) | Taxable income |
| `regular_tax_before_credits` | [regular_tax.md](regular_tax.md) | Combined regular tax |
| `total_gross_income_for_ftc` | [ftc_limitation.md](ftc_limitation.md) | FTC denominator |
| `general_ftc_limitation` | [ftc_limitation.md](ftc_limitation.md) | General limitation |
| `passive_ftc_limitation` | [ftc_limitation.md](ftc_limitation.md) | Passive limitation |
| `current_year_general_foreign_tax_usd` | [ftc_limitation.md](ftc_limitation.md) | General-basket tax input with manual posture |
| `allowed_general_ftc` | [allowed_ftc.md](allowed_ftc.md) | Allowed general FTC |
| `allowed_passive_ftc` | [allowed_ftc.md](allowed_ftc.md) | Allowed passive FTC |
| `us_source_dividends` | [treaty_resourcing.md](treaty_resourcing.md) | Treaty base |
| `treaty_resourcing_us_limitation` | [treaty_resourcing.md](treaty_resourcing.md) | Treaty worksheet U.S. limitation |
| `german_residual_tax_on_us_source_dividends` | [treaty_resourcing.md](treaty_resourcing.md) | Treaty cap assumption |
| `treaty_resourcing_additional_ftc` | [treaty_resourcing.md](treaty_resourcing.md) | Additional FTC |
| `total_allowed_ftc_after_treaty_resourcing` | [allowed_ftc.md](allowed_ftc.md) | Total allowed FTC after treaty-resourcing add-on |
| `net_investment_income` | [niit.md](niit.md) | NIIT base |
| `niit` | [niit.md](niit.md) | NIIT |
| `amt_amti` | [amt.md](amt.md) | AMTI base under § 55 / § 56 / § 57 |
| `amt_exemption` | [amt.md](amt.md) | § 55(d) exemption after phase-out |
| `amt_tentative_min_tax` | [amt.md](amt.md) | Tentative minimum tax after § 55(b) 26%/28% bracket |
| `amt_amtftc` | [amt.md](amt.md) | § 59 alternative minimum tax foreign tax credit |
| `amt_owed` | [amt.md](amt.md) | AMT = max(0, TMT after AMTFTC - regular tax) |
| `amt_owed_with_treaty_resourcing` | [amt.md](amt.md) | AMT under the treaty-resourcing scenario |
| `refund_if_positive_else_balance_due` | [payments_and_refund.md](payments_and_refund.md) | Baseline final result |
| `refund_if_positive_else_balance_due_with_treaty_resourcing` | [payments_and_refund.md](payments_and_refund.md) | Treaty scenario final result |
