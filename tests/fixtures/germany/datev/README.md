# DATEV Golden Case Fixtures

This directory is for DATEV example cases used as external golden tests.

Do not commit proprietary DATEV PDFs, ZIPs, exported data sets, or long copied case text. Instead, transcribe the minimum numeric facts and expected outputs needed to verify the engine into `provided_golden_cases.csv`, with a precise `source_reference` such as product, case name, page, and calculation-list date.

Run optional DATEV golden tests with:

```bash
DATEV_GERMANY_2025_GOLDEN_CASES=tests/fixtures/germany/datev/provided_golden_cases.csv python3 -m unittest tests.test_germany_2025_golden_sources
```

Required columns for `provided_golden_cases.csv`:

```csv
case_id,source_reference,source_url,filing_posture,people_count,other_income_22nr3_eur,other_income_22nr3_threshold_eur,prepayments_eur,person_1_display_name,person_1_gross_wage_eur,person_1_withheld_wage_tax_eur,person_1_withheld_solidarity_surcharge_eur,person_1_multiannual_wage_eur,person_1_employer_pension_contribution_eur,person_1_employee_pension_contribution_eur,person_1_employee_health_insurance_eur,person_1_employee_nursing_care_insurance_eur,person_1_employee_unemployment_insurance_eur,person_1_home_office_days_without_visit,person_1_home_office_days_with_visit,person_1_manual_work_equipment_deduction_eur,person_1_telecom_deduction_eur,person_1_employment_legal_insurance_deduction_eur,person_1_cross_border_tax_help_deduction_eur,person_1_health_insurance_sick_pay_reduction_rate,expected_joint_taxable_income_eur,expected_joint_income_tax_eur,expected_joint_soli_eur,expected_ordinary_refund_before_capital_eur
```

For joint cases, add the same `person_2_*` columns.
