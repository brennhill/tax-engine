# U.S. 2025 Alternative Minimum Tax (§ 55–§ 59)

## Authority

- `26 U.S.C. § 55` — alternative minimum tax imposed
- `26 U.S.C. § 56` — adjustments for AMTI
- `26 U.S.C. § 57` — preference items
- `26 U.S.C. § 59` — alternative minimum tax foreign tax credit (AMTFTC)
- Form `6251` — Alternative Minimum Tax — Individuals
- Rev. Proc. 2024-40 § 3.11 — 2025 inflation-adjusted AMT thresholds and exemption amounts
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section55&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section56&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section59&num=0&edition=prelim
  - https://www.irs.gov/forms-pubs/about-form-6251
  - https://www.irs.gov/pub/irs-drop/rp-24-40.pdf

## What This Rule Governs

The parallel U.S. tax computation under § 55 that compares regular tax to a
tentative minimum tax (TMT) on alternative-minimum-taxable income (AMTI) and
imposes the excess over regular tax as the alternative minimum tax (AMT).

## Inputs

- regular taxable income
- § 56 / § 57 add-backs (state/local tax itemized deductions, depreciation
  preferences, qualified-dividend / net-capital-gain treatment inside AMTI)
- 2025 § 55(d) exemption amounts and phase-out thresholds by filing status
- 2025 § 55(b) 26%/28% rate break point
- foreign-source income and category-allocated foreign taxes (§ 59 AMTFTC)
- treaty resourcing posture (§ 59 + § 904(d) parallel)

## Formula

1. Start from regular taxable income; add § 56 / § 57 preferences to reach
   AMTI.
2. Subtract the § 55(d) exemption (phased out at $0.25 per $1 of AMTI above
   the filing-status threshold) to reach taxable excess AMTI.
3. Apply the 26%/28% bracket at the 2025 rate-break point to reach
   tentative minimum tax (TMT) before AMTFTC.
4. Allow the § 59 AMTFTC against TMT subject to the parallel § 904(d)
   per-category limit on the AMTI base.
5. AMT = max(0, TMT after AMTFTC − regular tax). When treaty resourcing is
   elected, the AMT comparison is repeated on the resourced regular-tax
   side and the larger AMT result governs.

## Ordering

This stage runs after the regular-tax-before-credits stage and after the
baseline FTC stages (because the AMTFTC parallels § 904(d)). It runs
before the payment-reconciliation stage because AMT is added to regular
<!-- IRS-VERIFIED 2026-05-11 — full chain on 2025 Schedule 2 PDF -->
tax on Form 1040 line 17 via the Schedule 2 (2025 revision) chain:
<!-- IRS-VERIFIED 2026-05-11 — https://www.irs.gov/pub/irs-pdf/f1040s2.pdf -->
Form 6251 line 11 carries to Schedule 2 line 2; Schedule 2 line 3
sums line 1z (Part I additions to tax) and line 2 (AMT) and that
<!-- IRS-VERIFIED 2026-05-11 — f1040s2.pdf instructs the AMT row is line 2 -->
total is the value on Form 1040 line 17. AMT moved from Schedule 2
line 1 (2024 revision) to line 2 (2025 revision) — see
https://www.irs.gov/pub/irs-pdf/f1040s2.pdf — and the prior law-spec
<!-- IRS-VERIFIED 2026-05-11 — chain Form 6251 line 11 → Sched 2 line 2 → line 3 → 1040 line 17 -->
text described only the line-1 → line-2 shift without spelling out
the line-1z + line-2 sum.

## Rounding

- AMTI, exemption, taxable excess AMTI, TMT, and AMTFTC preserve cents;
  the final reported AMT and AMTFTC are quantized to cents at the rule
  output boundary.

## Edge Cases

- Phase-out can fully eliminate the exemption above the upper threshold,
  driving TMT to its full 26%/28% rate on AMTI.
- AMTFTC is computed independently of the regular-basket FTC; the
  resourced and non-resourced AMT comparisons each consume their own
  AMTFTC limit.
- § 55(b) preferential rates on the qualified-dividend / net-capital-gain
  slice of AMTI mirror the regular-tax preferential treatment.

## Ambiguities / Filing Positions

The 2025 inflation amounts come directly from Rev. Proc. 2024-40 § 3.11;
no ambiguity in the constants themselves. The AMTFTC source/category
allocation follows the same § 904(d) basket split used by the regular
FTC stages, so a posture change there propagates to AMT automatically.

## Implemented By

- `tax_pipeline/y2025/us_law.py` — § 55(d) exemption / phase-out and 26%/28%
  bracket constants
- `tax_pipeline/y2025/us_rules.py` — `US25-AMT-AMTI`, `US25-AMT-TENTATIVE`,
  and `US25-AMT-FTC-AND-COMPARE` stages

## Test Coverage

- `tests/test_us_amt_2025.py`

## Outputs Affected

- `years/<year>/outputs/analysis-steps/us-tax-trace.csv amt_amti`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv amt_exemption`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv amt_tentative_min_tax`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv amt_amtftc`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv amt_owed`
- `years/<year>/outputs/analysis-steps/us-tax-trace.csv amt_owed_with_treaty_resourcing`
- Form 6251 (rendered package)
