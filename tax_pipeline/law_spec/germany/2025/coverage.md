# Germany 2025 Law Spec Coverage

This file maps canonical Germany trace steps to law-spec files.

Every step in `years/<year>/outputs/analysis-steps/germany-model-trace.csv` should match at least one pattern below.

| Pattern | Rule Spec | Notes |
| --- | --- | --- |
| `joint_assessment_order` | [assessment_ordering.md](assessment_ordering.md) | Overall legal ordering |
| `person_*_gross_wage` | [employment_income.md](employment_income.md) | Wage facts |
| `person_*_equipment_*` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Equipment amounts and shares |
| `person_*_work_equipment` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Total work equipment |
| `person_*_home_office_deduction` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Home-office daily allowance |
| `person_*_telecom_deduction` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Telecom deduction |
| `person_*_employment_legal_insurance_deduction` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Legal-insurance share |
| `person_*_cross_border_tax_help_deduction` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Tax-advice share |
| `person_*_actual_werbungskosten` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Actual expenses |
| `person_*_allowed_werbungskosten` | [werbungskosten_and_work_expenses.md](werbungskosten_and_work_expenses.md) | Allowance comparison |
| `person_*_income_after_werbungskosten` | [employment_income.md](employment_income.md) | Net employment income |
| `person_*_employer_pension_contribution` | [retirement_contributions.md](retirement_contributions.md) | Employer pension share |
| `person_*_employee_pension_contribution` | [retirement_contributions.md](retirement_contributions.md) | Employee pension share |
| `person_*_retirement_contributions` | [retirement_contributions.md](retirement_contributions.md) | Deductible retirement amount |
| `person_*_health_gross` | [health_and_vorsorge.md](health_and_vorsorge.md) | Gross health contribution |
| `person_*_health_sick_pay_reduction` | [health_and_vorsorge.md](health_and_vorsorge.md) | Krankengeld component reduction |
| `person_*_nursing_care` | [health_and_vorsorge.md](health_and_vorsorge.md) | Nursing-care contribution |
| `person_*_health_and_nursing` | [health_and_vorsorge.md](health_and_vorsorge.md) | Basic health/nursing |
| `person_*_other_vorsorge_contributions` | [health_and_vorsorge.md](health_and_vorsorge.md) | Other Vorsorge |
| `person_*_other_vorsorge_allowed` | [health_and_vorsorge.md](health_and_vorsorge.md) | Cap-limited other Vorsorge |
| `person_*_special_expenses_total` | [health_and_vorsorge.md](health_and_vorsorge.md) | Per-person special expenses |
| `person_*_other_income_22nr3_taxable` | [other_income_22nr3.md](other_income_22nr3.md) | Per-spouse misc. income threshold |
| `other_income_22nr3_*` | [other_income_22nr3.md](other_income_22nr3.md) | Misc. income threshold |
| `altersentlastungsbetrag_*` | [altersentlastungsbetrag.md](altersentlastungsbetrag.md) | § 24a EStG age-relief allowance |
| `aussergewoehnliche_belastungen_*` | [aussergewoehnliche_belastungen.md](aussergewoehnliche_belastungen.md) | § 33 EStG außergewöhnliche Belastungen + zumutbare Belastung |
| `unterhaltsleistungen_*` | [unterhaltsleistungen.md](unterhaltsleistungen.md) | § 33a EStG Unterhaltsleistungen |
| `behinderung_pauschbetrag_*` | [behinderung_pauschbetrag.md](behinderung_pauschbetrag.md) | § 33b EStG Behinderten-Pauschbetrag |
| `spendenabzug_*` | [spendenabzug.md](spendenabzug.md) | § 10b EStG Spendenabzug |
| `arbeitszimmer_*` | [arbeitszimmer.md](arbeitszimmer.md) | § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer |
| `sum_income_after_werbungskosten` | [employment_income.md](employment_income.md) | Employment-income subtotal before § 22 income |
| `sum_of_income` | [assessment_ordering.md](assessment_ordering.md) | § 2 Abs. 3 sum of income after § 22 inclusion |
| `joint_other_vorsorge_cap` | [health_and_vorsorge.md](health_and_vorsorge.md) | Joint other-Vorsorge cap |
| `joint_other_vorsorge_health_nursing_consumed` | [health_and_vorsorge.md](health_and_vorsorge.md) | Health/nursing cap consumption |
| `total_special_expenses` | [health_and_vorsorge.md](health_and_vorsorge.md) | Joint special expenses |
| `joint_taxable_income` | [assessment_ordering.md](assessment_ordering.md) | Taxable-income stage |
| `joint_income_tax` | [basic_tariff.md](basic_tariff.md) | Basic tariff by default; legal-audit renderer remaps married `§ 32a Abs. 5` traces to split tariff |
| `joint_solidarity_surcharge` | [ordinary_soli.md](ordinary_soli.md) | Ordinary soli |
| `ordinary_refund_before_capital` | [payments_and_crediting.md](payments_and_crediting.md) | Ordinary-side crediting |
| `dher_stock_gain` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | DHER stock result |
| `stock_gain` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Stock bucket |
| `stock_loss_carryforward_2024` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Prior carryforward |
| `stock_loss_carryforward_used` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Used carryforward |
| `stock_gain_after_carryforward` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Post-carryforward stock gain |
| `fund_gain` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Fund gain bucket |
| `fund_taxable_after_teilfreistellung` | [equity_fund_teilfreistellung.md](equity_fund_teilfreistellung.md) | Fund taxable result after InvStG § 20/§ 21 |
| `option_gain` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Option bucket |
| `positive_income_total` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Positive income bucket |
| `combined_current_capital` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Combined current capital |
| `saver_allowance` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Saver allowance |
| `taxable_before_teilfreistellung` | [capital_buckets_and_saver_allowance.md](capital_buckets_and_saver_allowance.md) | Pre-Teilfreistellung taxable capital |
| `equity_fund_total` | [equity_fund_teilfreistellung.md](equity_fund_teilfreistellung.md) | Equity-fund amount |
| `teilfreistellung_reduction_base` | [equity_fund_teilfreistellung.md](equity_fund_teilfreistellung.md) | 30 percent reduction base |
| `taxable_after_teilfreistellung` | [equity_fund_teilfreistellung.md](equity_fund_teilfreistellung.md) | Post-Teilfreistellung base |
| `foreign_tax_1099_eur` | [capital_tax_ordering.md](capital_tax_ordering.md) | Foreign-tax credit input |
| `foreign_tax_credit_cap_eur` | [capital_tax_ordering.md](capital_tax_ordering.md) | Per-item §32d(5) cap |
| `capital_income_tax_no_teilfreistellung_after_foreign_tax` | [capital_tax_ordering.md](capital_tax_ordering.md) | No-Teilfreistellung capital tax |
| `capital_soli_no_teilfreistellung` | [capital_tax_ordering.md](capital_tax_ordering.md) | No-Teilfreistellung soli |
| `capital_tax_no_teilfreistellung` | [capital_tax_ordering.md](capital_tax_ordering.md) | No-Teilfreistellung total |
| `capital_income_tax_with_teilfreistellung_after_foreign_tax` | [capital_tax_ordering.md](capital_tax_ordering.md) | Post-Teilfreistellung capital tax |
| `capital_soli_with_teilfreistellung_before_treaty` | [capital_tax_ordering.md](capital_tax_ordering.md) | Capital soli before treaty |
| `capital_tax_with_teilfreistellung_before_treaty` | [capital_tax_ordering.md](capital_tax_ordering.md) | Total before treaty |
| `treaty_us_source_dividend_*` | [treaty_dividend_credit.md](treaty_dividend_credit.md) | U.S. treaty dividend item credit inside §32d(5) |
| `treaty_dividend_credit` | [treaty_dividend_credit.md](treaty_dividend_credit.md) | Explicit treaty amount |
| `capital_soli_with_teilfreistellung_after_treaty` | [capital_tax_ordering.md](capital_tax_ordering.md) | Post-treaty soli |
| `capital_income_tax_with_teilfreistellung_after_treaty` | [capital_tax_ordering.md](capital_tax_ordering.md) | Post-treaty tax |
| `capital_tax_with_teilfreistellung_after_treaty` | [capital_tax_ordering.md](capital_tax_ordering.md) | Post-treaty total |
| `refund_before_treaty` | [final_refund_assembly.md](final_refund_assembly.md) | Pre-treaty refund |
| `chosen_refund_before_domestic_certificate` | [final_refund_assembly.md](final_refund_assembly.md) | Post-treaty pre-domestic-certificate result |
| `bank_certificate_*` | [spouse_bank_capital_certificate.md](spouse_bank_capital_certificate.md) | Typed bank certificate facts integrated into capital assessment |
| `domestic_capital_withholding_credit` | [spouse_bank_capital_certificate.md](spouse_bank_capital_certificate.md) | Domestic KEST/soli withholding credit |
| `person_2_bank_certificate_*` | [spouse_bank_capital_certificate.md](spouse_bank_capital_certificate.md) | Spouse bank certificate |
| `private_sale_*` | [private_sales_carryforwards.md](private_sales_carryforwards.md) | Private-sale carryforward |
| `coinbase_private_sale_*` | [private_sales_carryforwards.md](private_sales_carryforwards.md) | Coinbase private-sale result |
| `final_target_refund` | [final_refund_assembly.md](final_refund_assembly.md) | Final result |
| `guenstigerpruefung_shadow_diff` | [guenstigerpruefung_shadow.md](guenstigerpruefung_shadow.md) | Audit-only § 32d Abs. 6 EStG shadow comparison (F-DE-2) |
