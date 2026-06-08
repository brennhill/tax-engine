# IRS 2025 MeF ATS Fixtures

This directory indexes official IRS Tax Year 2025 Form 1040-series MeF
Assurance Testing System scenarios.

Source page:
https://www.irs.gov/e-file-providers/tax-year-2025-form-1040-series-and-extensions-modernized-e-file-mef-assurance-testing-system-ats-information

The PDFs are not committed. They are official public IRS source documents, but
large binary copies would make the repository noisy. The fixture CSVs store:

- `source-options.csv`: the official IRS scenario index, source URLs, listed
  update dates, return family, and whether the current engine can use the case.
- `expected-form1040-lines.csv`: transcribed completed Form 1040 line values
  from IRS ATS scenario PDFs that expose completed line outputs in extractable
  text.
- `covered-engine-cases.csv`: the narrow executable oracle subset for lines
  that the current U.S. engine actually models. This intentionally excludes
  unsupported Schedule C, Schedule SE, nonrefundable credit, payment, refund,
  and amount-owed flows.

Important limitation: many ATS PDFs are submission/input scenarios and do not
expose completed Form 1040 output lines in text extraction. Those are still
indexed as source material, but they are not yet oracle cases for final line
outputs. They can become oracle tests after we add a robust PDF/form extraction
or manually verify the completed IRS form-line values.

Scenario 13 has one extra limitation: the official ATS draft return prints Form
1040 line 16 as `$162`, but the current IRS 2025 Form 1040 instructions Tax
Table row for taxable income `$1,600` to `$1,625` and married filing jointly is
`$161`. The executable current-law fixture therefore uses scenario 13 for line
15 taxable-income subtraction only and keeps line 16 as transcribed source
data, not as a green oracle.
