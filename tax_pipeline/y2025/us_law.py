from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, getcontext

from tax_pipeline._law_data import LAW_DATA as _LAW_DATA

getcontext().prec = 28

# Law-spec references:
# - tax_pipeline/law_spec/usa/2025/regular_tax.md
# - tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md
# - tax_pipeline/law_spec/usa/2025/capital_loss_limit.md
# - tax_pipeline/law_spec/usa/2025/ftc_limitation.md
# - tax_pipeline/law_spec/usa/2025/niit.md
# - tax_pipeline/law_spec/usa/2025/treaty_resourcing.md

USC_61_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61&num=0&edition=prelim"
USC_63_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63&num=0&edition=prelim"
# 26 U.S.C. § 164(f) — one-half of § 1401 SE tax (OASDI + Medicare,
# excluding § 1401(b)(2) Additional Medicare) is allowed as an
# above-the-line deduction in computing AGI. Lands on Schedule 1
# line 15 (and reduces Form 1040 line 10 / line 11 AGI).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164
USC_164_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164&num=0&edition=prelim"
USC_1_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim"
# 26 U.S.C. § 55 — alternative minimum tax (AMTI × 26%/28% over exemption,
# minus regular tax with FTC). § 55(b)(3) preserves § 1(h) preferential
# capital-gain / qualified-dividend rates inside the AMTI base.
# https://www.law.cornell.edu/uscode/text/26/55
USC_55_URL = "https://www.law.cornell.edu/uscode/text/26/55"
# 26 U.S.C. § 56 — AMTI add-backs (state/local tax itemized deduction,
# depreciation timing differences, ISO bargain element, NOL adjustments).
# https://www.law.cornell.edu/uscode/text/26/56
USC_56_URL = "https://www.law.cornell.edu/uscode/text/26/56"
# 26 U.S.C. § 59 — alternative minimum tax foreign tax credit (AMTFTC),
# parallels § 904(d) per-category limitation but uses the AMTI base.
# https://www.law.cornell.edu/uscode/text/26/59
USC_59_URL = "https://www.law.cornell.edu/uscode/text/26/59"
USC_901_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim"
USC_904_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim"
USC_1211_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211&num=0&edition=prelim"
USC_1212_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212&num=0&edition=prelim"
USC_1256_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256&num=0&edition=prelim"
USC_1411_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411&num=0&edition=prelim"
USC_6012_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6012&num=0&edition=prelim"
USC_6013_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6013&num=0&edition=prelim"
# 26 U.S.C. § 911 — Foreign Earned Income Exclusion (FEIE) and § 911(c)
# housing exclusion / deduction. § 911(d)(6) denies any deduction or
# credit allocable to the excluded amount (so excluded foreign earned
# income cannot also generate FTC). § 1411(d)(1)(A) requires the excluded
# amount to be added back to MAGI for NIIT purposes.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
USC_911_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911&num=0&edition=prelim"
# IRS Publication 54 — "Tax Guide for U.S. Citizens and Resident Aliens
# Abroad" — practical guidance for § 911 / § 911(c) and the bona-fide-
# residence (§ 911(d)(1)(A)) and physical-presence (§ 911(d)(1)(B)) tests.
# https://www.irs.gov/publications/p54
IRS_P54_URL = "https://www.irs.gov/publications/p54"
# IRS Form 2555 — "Foreign Earned Income" — the form on which the § 911
# election is reported.
# https://www.irs.gov/forms-pubs/about-form-2555
IRS_FORM_2555_URL = "https://www.irs.gov/forms-pubs/about-form-2555"
# IRS Notice 2024-77 — 2025 location-adjusted housing-exclusion limits
# (and the 30 %-of-FEIE statutory ceiling under § 911(c)(2)(A)).
# https://www.irs.gov/pub/irs-drop/n-24-77.pdf
IRS_NOTICE_2024_77_URL = "https://www.irs.gov/pub/irs-drop/n-24-77.pdf"
# 26 U.S.C. § 1401 / § 1402 — Self-Employment Contributions Act (SECA)
# tax: 12.4 % OASDI on net SE earnings (capped by the SSA wage base) plus
# 2.9 % Medicare on all net SE earnings, plus the § 1401(b)(2) 0.9 %
# additional Medicare tax above the same threshold as § 3101(b)(2).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
USC_1401_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401&num=0&edition=prelim"
USC_1402_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402&num=0&edition=prelim"
# 26 U.S.C. § 3101 — Federal Insurance Contributions Act (FICA): the
# employee Medicare tax (1.45 %) plus the § 3101(b)(2) Additional
# Medicare Tax (0.9 %) on wages above the threshold.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101
USC_3101_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101&num=0&edition=prelim"
# IRS Schedule SE — used to compute the § 1401 SE tax on net SE earnings.
# https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
IRS_SCHEDULE_SE_URL = "https://www.irs.gov/forms-pubs/about-schedule-se-form-1040"
# IRS Form 8959 — Additional Medicare Tax (§ 3101(b)(2) and § 1401(b)(2)).
# https://www.irs.gov/forms-pubs/about-form-8959
IRS_FORM_8959_URL = "https://www.irs.gov/forms-pubs/about-form-8959"
# Social Security Administration — U.S.-Germany Totalization Agreement
# (signed 1976-01-07; effective 1979-12-01). When a German-employer
# certificate of coverage exempts the wages from U.S. FICA/Medicare and
# SE tax, § 3101 / § 1401 do not attach.
# https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
SSA_TOTALIZATION_DE_URL = "https://www.ssa.gov/international/Agreement_Pamphlets/germany.html"
# 26 U.S.C. § 905(a) — paid-basis foreign tax credit election. By default
# the FTC is accrued for the tax year; § 905(a) lets the taxpayer elect
# cash-basis (paid-when-paid) timing, which is binding for that year and
# every subsequent year until revoked.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905
USC_905_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905&num=0&edition=prelim"
# IRS Form 8833 — Treaty-based return position disclosure under § 6114.
# Required when claiming treaty re-sourcing benefits (other than a small
# de-minimis exception) for a U.S. citizen/resident.
# https://www.irs.gov/forms-pubs/about-form-8833
IRS_FORM_8833_URL = "https://www.irs.gov/forms-pubs/about-form-8833"

# IRS "About Form X" landing pages — stable jump-off URLs used in
# FormLineRef.url. The pages link to the form, instructions, and recent
# revisions even after the IRS rotates the year-specific URL.
#
# Single-sourced here in the law module per CLAUDE.md "Tax-Law Rule
# Requirements". ``usa_2025_stages.py`` imports these constants — the
# pre-2026-05-03 split (parallel ``IRS_ABOUT_*`` constants in the
# stages module) was consolidated by the B-audit pass to keep one
# source of truth for every IRS form-landing URL.
IRS_ABOUT_FORM_1040_URL = "https://www.irs.gov/forms-pubs/about-form-1040"
IRS_ABOUT_FORM_1116_URL = "https://www.irs.gov/forms-pubs/about-form-1116"
IRS_ABOUT_FORM_6781_URL = "https://www.irs.gov/forms-pubs/about-form-6781"
IRS_ABOUT_FORM_8949_URL = "https://www.irs.gov/forms-pubs/about-form-8949"
IRS_ABOUT_FORM_8959_URL = "https://www.irs.gov/forms-pubs/about-form-8959"
IRS_ABOUT_FORM_8960_URL = "https://www.irs.gov/forms-pubs/about-form-8960"
IRS_ABOUT_SCHEDULE_1_URL = "https://www.irs.gov/pub/irs-pdf/f1040s1.pdf"
IRS_ABOUT_SCHEDULE_2_URL = "https://www.irs.gov/pub/irs-pdf/f1040s2.pdf"
IRS_ABOUT_SCHEDULE_3_URL = "https://www.irs.gov/pub/irs-pdf/f1040s3.pdf"
IRS_ABOUT_SCHEDULE_D_URL = "https://www.irs.gov/forms-pubs/about-schedule-d-form-1040"
IRS_ABOUT_SCHEDULE_SE_URL = "https://www.irs.gov/forms-pubs/about-schedule-se-form-1040"

# IRS Free File — the public IRS endpoint for the do-it-yourself
# filing path many small filers use. Cited by the per-jurisdiction
# filing-guide renderer.
# https://www.irs.gov/filing/free-file-do-your-federal-taxes-for-free
IRS_FREE_FILE_URL = "https://www.irs.gov/filing/free-file-do-your-federal-taxes-for-free"

IRS_I1040 = "https://www.irs.gov/instructions/i1040gi"
IRS_I1040SD = "https://www.irs.gov/instructions/i1040sd"
IRS_I1116 = "https://www.irs.gov/instructions/i1116"
IRS_I1099B = "https://www.irs.gov/instructions/i1099b"
IRS_I8949 = "https://www.irs.gov/instructions/i8949"
IRS_I8960 = "https://www.irs.gov/instructions/i8960"
IRS_P514 = "https://www.irs.gov/publications/p514"
IRS_P525 = "https://www.irs.gov/publications/p525"
IRS_P550 = "https://www.irs.gov/publications/p550"
# IRS Form 6251 Alternative Minimum Tax — Individuals, instructions and form.
# https://www.irs.gov/forms-pubs/about-form-6251
FORM_6251_INSTRUCTIONS_URL = "https://www.irs.gov/forms-pubs/about-form-6251"
# Rev. Proc. 2024-40 (2025 inflation adjustments — exemption, phase-out, and
# 26%/28% rate-break amounts under § 55(d), § 55(b)).
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
REV_PROC_2024_40_URL = "https://www.irs.gov/pub/irs-drop/rp-24-40.pdf"
IRS_YEARLY_AVG_RATES = "https://www.irs.gov/individuals/international-taxpayers/yearly-average-currency-exchange-rates"
# Pinned 2025 Euro Zone yearly average rate (EUR per USD). The IRS publishes
# this in Q1 of the following year on the page above. The value used here is
# the 2025 figure read from years/<year>/normalized/reference-data/us-tax-constants.csv
# row `eur_per_usd_yearly_average_2025` (sourced `irs_2025_yearly_average_rates`).
# Tests in tests/y2025/test_us_law.py pin both the value and the source attribution.
# NOTE (L13, 2026-05-01 correctness review): if the IRS restates the 2025
# rate, both this literal AND the ``us-tax-constants.csv`` row must be
# updated together. The pinned literal is deliberately retained so the
# legal layer is independent of workspace CSV state during tests; do not
# replace it with a CSV read at module import time.
IRS_YEARLY_AVG_2025_EURO_ZONE = Decimal("0.886")
IRS_GERMANY_TECH = "https://www.irs.gov/pub/irs-trty/germtech.pdf"
IRS_DIGITAL_ASSETS = "https://www.irs.gov/filing/digital-assets"

MFS_CAPITAL_LOSS_LIMIT_USD = _LAW_DATA["MFS_CAPITAL_LOSS_LIMIT_USD"]
STANDARD_CAPITAL_LOSS_LIMIT_USD = _LAW_DATA["STANDARD_CAPITAL_LOSS_LIMIT_USD"]
# IRC § 1(h)(1)(C) — qualified-dividend / long-term capital-gain 15 % bracket.
# https://www.law.cornell.edu/uscode/text/26/1
# Numerically coincident with DBA-USA Art. 10(2)(b) but legally independent.
QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE = _LAW_DATA["QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE"]
# IRC § 1(h)(1)(D) — qualified-dividend / long-term capital-gain 20 % bracket.
QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE = _LAW_DATA["QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE"]
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE as _DBA_ART_10_2_B_RATE,
)

TREATY_DIVIDEND_RATE = _DBA_ART_10_2_B_RATE
NIIT_RATE = _LAW_DATA["NIIT_RATE"]
SECTION_1256_SHORT_RATIO = _LAW_DATA["SECTION_1256_SHORT_RATIO"]
SECTION_1256_LONG_RATIO = _LAW_DATA["SECTION_1256_LONG_RATIO"]
FORM_1116_PREFERENTIAL_EXCEPTION_LIMIT_USD = Decimal("20000.00")

# ---------------------------------------------------------------------------
# Alternative Minimum Tax constants (§ 55 / § 56 / § 59)
# ---------------------------------------------------------------------------
# 26 U.S.C. § 55(d) AMT exemption amounts for 2025, indexed under § 55(d)(4)
# and published in Rev. Proc. 2024-40 § 3.11:
#   - Single / unmarried (other than a surviving spouse): $88,100
#   - Married filing jointly / surviving spouse: $137,000
#   - Married filing separately: $68,500 (= MFJ exemption / 2)
# https://www.law.cornell.edu/uscode/text/26/55
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
AMT_EXEMPTION_SINGLE_2025_USD = _LAW_DATA["AMT_EXEMPTION_SINGLE_2025_USD"]
AMT_EXEMPTION_MFJ_2025_USD = _LAW_DATA["AMT_EXEMPTION_MFJ_2025_USD"]
AMT_EXEMPTION_MFS_2025_USD = _LAW_DATA["AMT_EXEMPTION_MFS_2025_USD"]
# § 55(d)(3) phase-out: the exemption is reduced by 25 cents per dollar of
# AMTI above the threshold. 2025 thresholds (Rev. Proc. 2024-40 § 3.11):
#   - Single / unmarried: $626,350
#   - Married filing jointly / surviving spouse: $1,252,700
#   - Married filing separately: $626,350 (= MFJ / 2)
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
AMT_PHASEOUT_START_SINGLE_2025_USD = _LAW_DATA["AMT_PHASEOUT_START_SINGLE_2025_USD"]
AMT_PHASEOUT_START_MFJ_2025_USD = _LAW_DATA["AMT_PHASEOUT_START_MFJ_2025_USD"]
AMT_PHASEOUT_START_MFS_2025_USD = _LAW_DATA["AMT_PHASEOUT_START_MFS_2025_USD"]
# § 55(d)(3) reduction rate: $0.25 of exemption lost per $1.00 of AMTI excess.
AMT_PHASEOUT_RATE = _LAW_DATA["AMT_PHASEOUT_RATE"]
# § 55(b)(1) tentative minimum tax rates: 26% on the first portion of
# (AMTI - exemption), 28% on the remainder. For 2025 the 26%/28% break is
# at $239,100 of taxable excess AMTI (Rev. Proc. 2024-40 § 3.11), halved to
# $119,550 for MFS under § 55(b)(1)(A)(ii)(II).
AMT_RATE_LOW = _LAW_DATA["AMT_RATE_LOW"]
AMT_RATE_HIGH = _LAW_DATA["AMT_RATE_HIGH"]
AMT_RATE_BREAK_2025_USD = _LAW_DATA["AMT_RATE_BREAK_2025_USD"]
AMT_RATE_BREAK_MFS_2025_USD = _LAW_DATA["AMT_RATE_BREAK_MFS_2025_USD"]

USD_CENT = Decimal("0.01")
ZERO_USD = Decimal("0.00")

# ---------------------------------------------------------------------------
# FATCA Form 8938 + FinCEN Form 114 (FBAR) — 2025 reporting thresholds
# ---------------------------------------------------------------------------
# Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): 26 U.S.C. § 6038D / Reg.
# § 1.6038D-2 establish Form 8938 ("Statement of Specified Foreign
# Financial Assets") reporting for individuals holding "specified
# foreign financial assets" above filing-status- and residency-
# dependent thresholds. 31 U.S.C. § 5314 / 31 CFR § 1010.350 establish
# the FinCEN Form 114 ("Report of Foreign Bank and Financial Accounts" /
# FBAR) reporting for U.S. persons with aggregate foreign financial
# accounts > $10,000 at any point during the calendar year. The two
# regimes overlap but are distinct: FBAR is filed with FinCEN
# (separately from the income tax return), Form 8938 is attached to
# Form 1040.
#
# Form 8938 thresholds (Reg. § 1.6038D-2(b), 2025 IRS Form 8938
# instructions):
#   - Single / MFS / HoH living in the U.S.: $50,000 EOY | $75,000 anytime.
#   - MFJ living in the U.S.:                $100,000 EOY | $150,000 anytime.
#   - Single / MFS / HoH living abroad:      $200,000 EOY | $300,000 anytime.
#   - MFJ living abroad:                     $400,000 EOY | $600,000 anytime.
#
# "Living abroad" test — Reg. § 1.6038D-2(b)(1): bona-fide resident of
# a foreign country under § 911(d)(1)(A) for the year, OR present in
# foreign countries at least 330 days of any 12-month period ending in
# the tax year. The brenn-2025 posture (U.S. citizen, MFS, resident in
# Berlin) qualifies under § 911(d)(1)(A); the engine reads the
# residency basis from ``profile.json`` and the FATCA / FBAR rule
# selects the abroad-tier thresholds accordingly.
#
# FBAR threshold: 31 CFR § 1010.350(a) — "foreign financial accounts
# exceeding $10,000" aggregate at any time during the calendar year.
# FBAR scope is broader than Form 8938 § 6038D scope (e.g. signature-
# only authority on a non-owned account triggers FBAR but not always
# Form 8938).
#
# Authority URLs:
#   - 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
#   - 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
#   - IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
#   - 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
#   - 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
#   - FinCEN BSA E-Filing — https://bsaefiling.fincen.treas.gov/
#   - IRS comparison of Form 8938 vs FBAR —
#     https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements
USC_6038D_URL = "https://www.law.cornell.edu/uscode/text/26/6038D"
CFR_1_6038D_2_URL = "https://www.law.cornell.edu/cfr/text/26/1.6038D-2"
IRS_FORM_8938_URL = "https://www.irs.gov/forms-pubs/about-form-8938"
USC_31_5314_URL = "https://www.law.cornell.edu/uscode/text/31/5314"
CFR_31_1010_350_URL = "https://www.law.cornell.edu/cfr/text/31/1010.350"
FINCEN_BSA_EFILING_URL = "https://bsaefiling.fincen.treas.gov/"
IRS_FORM_8938_VS_FBAR_URL = "https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements"

# Form 8938 thresholds (Reg. § 1.6038D-2(b), 2025 instructions). Pinned
# as named constants per invariant I1; if the IRS/Treasury raises any
# threshold, edit here only and tests pin the numerics.
FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_EOY_USD = Decimal("50000")
FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_ANYTIME_USD = Decimal("75000")
FATCA_8938_THRESHOLD_DOMESTIC_MFJ_EOY_USD = Decimal("100000")
FATCA_8938_THRESHOLD_DOMESTIC_MFJ_ANYTIME_USD = Decimal("150000")
FATCA_8938_THRESHOLD_ABROAD_SINGLE_EOY_USD = Decimal("200000")
FATCA_8938_THRESHOLD_ABROAD_SINGLE_ANYTIME_USD = Decimal("300000")
FATCA_8938_THRESHOLD_ABROAD_MFJ_EOY_USD = Decimal("400000")
FATCA_8938_THRESHOLD_ABROAD_MFJ_ANYTIME_USD = Decimal("600000")

# FBAR threshold (31 CFR § 1010.350(a)).
FBAR_AGGREGATE_THRESHOLD_USD = Decimal("10000")

# ---------------------------------------------------------------------------
# § 911 Foreign Earned Income Exclusion + § 911(c) Housing Exclusion (2025)
# ---------------------------------------------------------------------------
# 26 U.S.C. § 911(b)(2)(D) base FEIE for 2025: $130,000 (Rev. Proc. 2024-40
# § 3.34). § 911(c)(1)(B) base housing amount = 16 % of FEIE ($20,800 for
# 2025). § 911(c)(2)(A) caps the housing-cost ceiling at 30 % of the
# § 911 exclusion ($39,000 default for 2025) before the IRS Notice
# 2024-77 location adjustment.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
# https://www.irs.gov/pub/irs-drop/n-24-77.pdf
SECTION_911_FEIE_2025_USD = _LAW_DATA["SECTION_911_FEIE_2025_USD"]
SECTION_911_HOUSING_BASE_RATE = _LAW_DATA["SECTION_911_HOUSING_BASE_RATE"]
SECTION_911_HOUSING_CEILING_RATE = _LAW_DATA["SECTION_911_HOUSING_CEILING_RATE"]

# ---------------------------------------------------------------------------
# § 1401 / § 3101 Self-Employment + Additional Medicare (2025)
# ---------------------------------------------------------------------------
# 26 U.S.C. § 1402(a)(12) — only 92.35 % of net SE earnings is subject to
# SE tax (the residual 7.65 % approximates the employer-share deduction).
# § 1401(a) imposes 12.4 % OASDI; § 1401(b)(1) imposes 2.9 % Medicare on
# the same base. § 1401(b)(2) imposes an additional 0.9 % Medicare tax
# above the § 3101(b)(2) thresholds. § 3101(b)(2) imposes the same
# 0.9 % additional Medicare tax on wages above the wage threshold.
# 2025 Social Security (OASDI) wage base: $176,100 (SSA Press Release
# 2024-10-10). Additional Medicare thresholds are statutory and do not
# inflation-index: $200,000 (Single / HoH), $250,000 (MFJ), $125,000
# (MFS), per § 3101(b)(2)(A)-(C).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101
# https://www.ssa.gov/oact/cola/cbb.html
SECA_NET_EARNINGS_FACTOR = _LAW_DATA["SECA_NET_EARNINGS_FACTOR"]
OASDI_RATE = _LAW_DATA["OASDI_RATE"]
MEDICARE_RATE = _LAW_DATA["MEDICARE_RATE"]
ADDITIONAL_MEDICARE_RATE = _LAW_DATA["ADDITIONAL_MEDICARE_RATE"]
EMPLOYEE_MEDICARE_RATE = _LAW_DATA["EMPLOYEE_MEDICARE_RATE"]
SS_WAGE_BASE_2025_USD = _LAW_DATA["SS_WAGE_BASE_2025_USD"]
ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD = _LAW_DATA["ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD"]
ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD = _LAW_DATA["ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD"]
ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD = _LAW_DATA["ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD"]

# ---------------------------------------------------------------------------
# § 24 Child Tax Credit + Credit for Other Dependents (Schedule 8812, 2025)
# ---------------------------------------------------------------------------
# 26 U.S.C. § 24(a) — Child Tax Credit per qualifying child (defined in
# § 152(c)) under age 17 with a valid SSN under § 24(h)(7). Post-OBBBA,
# § 24(h)(2) substitutes $2,200 for the § 24(a) base for 2025 — confirmed
# against IRS Schedule 8812 (2025) instructions ("the maximum amount of
# CTC for each qualifying child increased to $2,200") and the IRS Child
# Tax Credit landing page.
# 26 U.S.C. § 24(d)(1)(A) — refundable portion (Additional Child Tax
# Credit / ACTC) capped at $1,700 per qualifying child for 2025. The cap
# is inflation-indexed via § 24(h)(5) and published in Rev. Proc.
# 2024-40 § 3.05 ("Child Tax Credit") — NOT § 3.39 (which is the FEIE).
# 26 U.S.C. § 24(h)(4) — $500 Credit for Other Dependents (ODC) for a
# qualifying child age 17+ or a qualifying relative with a TIN.
# 26 U.S.C. § 24(b) — phase-out begins at $200,000 (single/HoH/MFS) and
# $400,000 (MFJ); the credit is reduced by $50 for each $1,000
# (or fraction thereof) of modified AGI above the threshold.
# 26 U.S.C. § 24(d)(1) — refundable ACTC formula: 15 % × (earned income
# − $2,500), capped at $1,700 per qualifying child (the ACTC cap);
# the nonrefundable portion is capped by regular tax after FTC.
#
# Authority URLs:
# https://www.law.cornell.edu/uscode/text/26/24
# https://www.law.cornell.edu/uscode/text/26/152
# https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
# https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
USC_24_URL = "https://www.law.cornell.edu/uscode/text/26/24"
USC_152_URL = "https://www.law.cornell.edu/uscode/text/26/152"
SCH_8812_INSTRUCTIONS_URL = "https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040"
CTC_PER_CHILD_2025_USD = _LAW_DATA["CTC_PER_CHILD_2025_USD"]
# Refundable ACTC cap per qualifying child — $1,700 for 2025
# (§ 24(d)(1)(A); inflation-indexed via § 24(h)(5); Rev. Proc. 2024-40
# § 3.05). If a future statute raises this cap, update this constant
# AND the law spec entry — the test suite pins the numeric value so a
# silent change cannot land.
CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD = _LAW_DATA["CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD"]
ODC_PER_DEPENDENT_2025_USD = _LAW_DATA["ODC_PER_DEPENDENT_2025_USD"]
CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD = _LAW_DATA["CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD"]
CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD = _LAW_DATA["CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD"]
# § 24(b)(2) — $50 reduction per $1,000 of MAGI excess = 5 percentage
# points per $1,000, applied to the rounded-up thousand-dollar excess.
CTC_PHASEOUT_RATE = _LAW_DATA["CTC_PHASEOUT_RATE"]
# § 24(d)(1)(B) — earned income floor below which no refundable ACTC is
# generated.
CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD = _LAW_DATA["CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD"]
# § 24(d)(1)(B) — 15 % phase-in rate on earned income above the floor.
CTC_REFUNDABLE_PHASE_IN_RATE = _LAW_DATA["CTC_REFUNDABLE_PHASE_IN_RATE"]

NON_RULE_PUBLIC_HELPERS_2025 = {
    "round_cents",
    # Schedule B precondition predicates: the IRS Form 1040 Instructions
    # gate Schedule B rendering on (interest > $1,500) OR (dividends >
    # $1,500) OR (foreign account exists). The predicate itself does not
    # change any tax line — it determines whether Schedule B is rendered
    # at all — so it is consulted by the form renderer rather than
    # owning a rule-graph stage. Authority: IRS Form 1040 Instructions
    # (i1040gi) and About Schedule B Form 1040.
    # https://www.irs.gov/instructions/i1040gi
    # https://www.irs.gov/forms-pubs/about-schedule-b-form-1040
    "schedule_b_required_2025",
    "schedule_b_parts_required_2025",
}

REGISTERED_LAW_FUNCTIONS_2025 = {
    "form_1040_whole_dollar_2025": ("US25-09-REGULAR-TAX", "US25-21-PAYMENTS"),
    "validate_supported_us_filing_positions_2025": ("US25-00-FILING-POSITION",),
    "validate_us_assessment_source_amounts_2025": ("US25-00-FILING-POSITION",),
    "validate_treaty_resourcing_dividend_split_2025": ("US25-15-TREATY-US-SOURCE-DIVIDENDS",),
    "validate_treaty_resourcing_inputs_2025": (
        "US25-15-TREATY-US-SOURCE-DIVIDENDS",
        "US25-16-TREATY-AVERAGE-TAX-FLOOR",
        "US25-17-TREATY-GERMAN-RESIDUAL-CAP",
        "US25-18-TREATY-ADDITIONAL-FTC",
    ),
    "validate_us_source_split_inputs_2025": ("US25-15-TREATY-US-SOURCE-DIVIDENDS",),
    "validate_germany_treaty_dividend_coverage_2025": ("US25-17-TREATY-GERMAN-RESIDUAL-CAP",),
    "section_1256_split_2025": ("US25-04-SECTION-1256",),
    "compute_capital_assessment_2025": (
        "US25-03-CAPITAL-BUCKETS",
        "US25-04-SECTION-1256",
        "US25-05-CAPITAL-LOSS-LINE-7A",
        "US25-06-PREFERENTIAL-CAPITAL-BASE",
    ),
    "net_capital_gain_for_preferential_tax_2025": (
        "US25-06-PREFERENTIAL-CAPITAL-BASE",
        "US25-09-REGULAR-TAX",
    ),
    "wages_usd_2025": ("US25-01-WAGE-TRANSLATION",),
    "adjusted_gross_income_2025": ("US25-07-AGI",),
    "taxable_income_2025": ("US25-08-TAXABLE-INCOME",),
    "tax_from_schedule_y2_2025": ("US25-09-REGULAR-TAX",),
    "tax_from_schedule_y2_2025_mfs": ("US25-09-REGULAR-TAX",),
    "regular_tax_2025": ("US25-09-REGULAR-TAX",),
    "regular_tax_2025_mfs": ("US25-09-REGULAR-TAX",),
    "total_gross_income_for_ftc_2025": ("US25-11-FTC-DENOMINATOR",),
    "validate_documented_positive_income_denominator_bound_2025": ("US25-11-FTC-DENOMINATOR",),
    "standard_deduction_allocation_2025": ("US25-11-FTC-DENOMINATOR",),
    "ftc_limitation_2025": ("US25-12-FTC-LIMITATIONS",),
    "validate_form_1116_preferential_adjustment_support_2025": ("US25-10-FORM-1116-PREFERENTIAL-GATE",),
    "current_year_general_foreign_tax_usd_2025": ("US25-13-FOREIGN-TAX-AVAILABLE",),
    "allowed_ftc_2025": ("US25-19-ALLOWED-FTC",),
    "compute_ftc_assessment_2025": (
        "US25-10-FORM-1116-PREFERENTIAL-GATE",
        "US25-11-FTC-DENOMINATOR",
        "US25-12-FTC-LIMITATIONS",
        "US25-13-FOREIGN-TAX-AVAILABLE",
        "US25-14-BASELINE-ALLOWED-FTC",
        "US25-19-ALLOWED-FTC",
    ),
    "treaty_resourcing_assessment_2025": (
        "US25-15-TREATY-US-SOURCE-DIVIDENDS",
        "US25-16-TREATY-AVERAGE-TAX-FLOOR",
        "US25-17-TREATY-GERMAN-RESIDUAL-CAP",
        "US25-18-TREATY-ADDITIONAL-FTC",
    ),
    "niit_assessment_2025": ("US25-20-NIIT",),
    # F-US-1: Alternative Minimum Tax under 26 U.S.C. §§ 55, 56, 59. Each
    # public helper participates in the AMT stage chain (US25-AMT-AMTI through
    # US25-AMT-FTC-AND-COMPARE). Authority cited near the function bodies.
    "amt_exemption_after_phaseout_2025": ("US25-AMT-TENTATIVE",),
    "amt_tentative_minimum_tax_2025": ("US25-AMT-TENTATIVE",),
    "amt_owed_2025": ("US25-AMT-FTC-AND-COMPARE",),
    # § 911 FEIE / § 1401 SE / § 3101(b)(2) Additional Medicare helpers.
    "feie_assessment_2025": ("US25-FEIE",),
    "se_tax_assessment_2025": ("US25-SE-TAX",),
    "additional_medicare_assessment_2025": ("US25-ADDITIONAL-MEDICARE",),
    # 26 U.S.C. § 6038D + 31 CFR § 1010.350 — Form 8938 / FBAR
    # determination (Group D, FORM-MAPPING-FOLLOWUP, 2026-05-03). The
    # rule produces booleans + threshold scalars only; it does not
    # affect tax owed.
    "fatca_fbar_assessment_2025": ("US25-FATCA-FBAR-DETERMINATION",),
    # 26 U.S.C. § 24 Child Tax Credit + Credit for Other Dependents.
    "ctc_and_odc_assessment_2025": ("US25-CTC-AND-ODC",),
    "compute_us_assessment_2025": (
        "US25-00-FILING-POSITION",
        "US25-01-WAGE-TRANSLATION",
        "US25-02-INCOME-SIDE-INPUTS",
        "US25-03-CAPITAL-BUCKETS",
        "US25-04-SECTION-1256",
        "US25-05-CAPITAL-LOSS-LINE-7A",
        "US25-06-PREFERENTIAL-CAPITAL-BASE",
        # F-C1: US25-SE-TAX runs before US25-07-AGI so the § 164(f) one-half
        # SE-tax deduction reduces AGI. Downstream consumers
        # (US25-ADDITIONAL-MEDICARE, US25-21-PAYMENTS) read the same
        # ``us.stage.se_tax`` output.
        "US25-SE-TAX",
        "US25-07-AGI",
        "US25-08-TAXABLE-INCOME",
        "US25-09-REGULAR-TAX",
        "US25-10-FORM-1116-PREFERENTIAL-GATE",
        "US25-11-FTC-DENOMINATOR",
        "US25-12-FTC-LIMITATIONS",
        "US25-13-FOREIGN-TAX-AVAILABLE",
        "US25-14-BASELINE-ALLOWED-FTC",
        "US25-15-TREATY-US-SOURCE-DIVIDENDS",
        "US25-16-TREATY-AVERAGE-TAX-FLOOR",
        "US25-17-TREATY-GERMAN-RESIDUAL-CAP",
        "US25-18-TREATY-ADDITIONAL-FTC",
        "US25-19-ALLOWED-FTC",
        "US25-FEIE",
        "US25-AMT-AMTI",
        "US25-AMT-TENTATIVE",
        "US25-AMT-FTC-AND-COMPARE",
        "US25-ADDITIONAL-MEDICARE",
        "US25-CTC-AND-ODC",
        "US25-20-NIIT",
        "US25-21-PAYMENTS",
    ),
}


def round_cents(value: Decimal) -> Decimal:
    # U.S. supporting workpapers are audited at the cent level before form-level rounding.
    return value.quantize(USD_CENT, rounding=ROUND_HALF_UP)


def form_1040_whole_dollar_2025(value: Decimal) -> Decimal:
    # IRS Form 1040 instructions allow whole-dollar entries on the filed form:
    # https://www.irs.gov/instructions/i1040gi. Keep this separate from cent-level
    # legal workpapers so audit outputs do not lose precision.
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(USD_CENT)


def _require_non_negative(value: Decimal, *, label: str) -> None:
    if value < ZERO_USD:
        raise ValueError(f"{label} must be non-negative")


def _require_positive(value: Decimal, *, label: str) -> None:
    if value <= ZERO_USD:
        raise ValueError(f"{label} must be positive")


def _require_unit_interval(value: Decimal, *, label: str) -> None:
    if value < ZERO_USD or value > Decimal("1.00"):
        raise ValueError(f"{label} must be between 0 and 1 inclusive")


@dataclass(frozen=True)
class USTaxConstants2025:
    # Posture-neutral 2025 IRS-published constants. The loader at
    # tax_pipeline/y2025/us_inputs.py:289 picks the row whose key matches the
    # taxpayer's filing posture from years/<year>/normalized/reference-data/
    # us-tax-constants.csv and stuffs that single posture's value into each
    # field. Authority: Rev. Proc. 2024-40 (2025 inflation adjustments) and
    # IRS Form 1040 Instructions for 2025.
    # https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
    eur_per_usd_yearly_average_2025: Decimal
    standard_deduction_2025_usd: Decimal
    capital_loss_limit_usd: Decimal
    niit_threshold_usd: Decimal
    qualified_dividend_zero_rate_ceiling_2025_usd: Decimal
    qualified_dividend_fifteen_rate_ceiling_2025_usd: Decimal
    tax_bracket_10_ceiling_2025_usd: Decimal
    tax_bracket_12_ceiling_2025_usd: Decimal
    tax_bracket_22_ceiling_2025_usd: Decimal
    tax_bracket_24_ceiling_2025_usd: Decimal
    tax_bracket_32_ceiling_2025_usd: Decimal
    tax_bracket_35_ceiling_2025_usd: Decimal


@dataclass(frozen=True)
class USCapitalSourceFacts2025:
    ordinary_dividends_usd: Decimal
    qualified_dividends_usd: Decimal
    capital_gain_distributions_usd: Decimal
    nondividend_distributions_usd: Decimal
    foreign_tax_paid_usd: Decimal
    interest_income_usd: Decimal
    substitute_payments_usd: Decimal
    staking_income_usd: Decimal
    estimated_payment_2025_usd: Decimal
    passive_ftc_carryover_2024_usd: Decimal
    general_ftc_carryover_2024_usd: Decimal
    german_2024_redetermination_paid_2025_eur: Decimal
    schwab_short_box_a_gain_usd: Decimal
    schwab_short_box_b_gain_usd: Decimal
    schwab_long_box_d_gain_usd: Decimal
    schwab_section_1256_total_usd: Decimal
    jpm_short_type_a_gain_usd: Decimal
    coinbase_short_with_basis_proceeds_usd: Decimal
    coinbase_short_with_basis_basis_usd: Decimal
    coinbase_short_unknown_proceeds_usd: Decimal
    coinbase_short_unknown_basis_reconstructed_usd: Decimal
    coinbase_long_with_basis_proceeds_usd: Decimal
    coinbase_long_with_basis_basis_usd: Decimal


@dataclass(frozen=True)
class USFTCInputs2025:
    taxpayer_gross_wages_eur: Decimal
    spouse_gross_wages_eur: Decimal
    joint_wage_side_tax_eur: Decimal
    foreign_source_passive_dividends_usd: Decimal
    foreign_source_qualified_dividends_usd: Decimal
    foreign_source_net_capital_gain_usd: Decimal
    known_positive_short_capital_gain_usd: Decimal
    known_positive_long_capital_gain_usd: Decimal
    conservative_positive_income_only: bool
    allocate_joint_german_tax_by_wage_share: bool


@dataclass(frozen=True)
class USTreatyDividendItem2025:
    item_id: str
    treaty_bucket: str
    gross_dividend_usd: Decimal


@dataclass(frozen=True)
class GermanyTreatyDividendPacketItem2025:
    item_id: str
    owner_slot: str
    dividend_class: str
    gross_dividend_eur: Decimal
    gross_dividend_usd: Decimal
    german_taxable_dividend_eur: Decimal
    article_10_source_tax_ceiling_usd: Decimal
    german_precredit_tax_on_us_source_dividend_usd: Decimal
    german_residence_credit_for_us_tax_usd: Decimal
    fx_reconciliation: str


@dataclass(frozen=True)
class USTreatyInputs2025:
    use_treaty_resourcing: bool
    us_source_direct_equity_dividends_usd: Decimal
    us_source_equity_fund_dividends_usd: Decimal
    us_source_non_equity_fund_dividends_usd: Decimal
    us_treaty_dividend_items: tuple[USTreatyDividendItem2025, ...] = ()
    germany_treaty_dividend_items: tuple[GermanyTreatyDividendPacketItem2025, ...] = ()
    germany_treaty_us_source_dividend_gross_usd: Decimal | None = None
    germany_treaty_us_source_dividend_allowed_us_tax_usd: Decimal | None = None
    german_precredit_tax_on_us_source_dividends_usd: Decimal | None = None
    german_residence_credit_for_us_tax_usd: Decimal | None = None
    # DBA-USA Art. 28 (Limitation on Benefits) qualification category
    # (Workstream 4). Default ``"qualified_resident"`` matches the
    # typical posture for a U.S.-citizen-in-Germany individual under
    # Art. 28(2)(a) qualified-resident test. Closed-enum membership is
    # validated by ``treaty25_lob_qualification`` against
    # ``LOB_QUALIFICATION_CATEGORIES`` in
    # ``tax_pipeline/y2025/treaty_law.py``.
    lob_qualification_category: str = "qualified_resident"


@dataclass(frozen=True)
class USReturnProfile2025:
    filing_status_label: str
    spouse_name_for_mfs_line: str
    joint_return_spouse_name: str
    joint_return_with_nra_spouse_election: bool
    accrued_basis_ftc: bool
    include_staking_in_niit: bool


@dataclass(frozen=True)
class USFEIEInputs2025:
    """26 U.S.C. § 911 Foreign Earned Income Exclusion election state.

    When ``elected`` is False, every other field is zero and the FEIE
    stage emits zeros. When ``elected`` is True the loader requires:
      - ``foreign_earned_income_usd`` — § 911(b) gross foreign earned
        income (wages, SE earnings, professional fees) earned while
        present abroad. Limited to ``SECTION_911_FEIE_2025_USD`` by
        § 911(b)(2)(D).
      - ``qualifying_test`` — ``"bona_fide_residence"`` (§ 911(d)(1)(A))
        or ``"physical_presence"`` (§ 911(d)(1)(B)).
      - ``housing_expenses_usd`` — § 911(c)(1) qualifying housing
        expenses incurred for the tax home.
      - ``location_adjusted_housing_ceiling_usd`` — IRS Notice 2024-77
        location-adjusted housing-cost ceiling. ``None`` falls back to
        the § 911(c)(2)(A) statutory 30 %-of-FEIE default.
      - ``self_employed`` — when True, § 911(c)(4)(A) routes the housing
        amount to the § 911(c)(4) deduction (vs. exclusion for employees).
      - ``foreign_tax_paid_on_excluded_income_usd`` — foreign tax that
        would otherwise be creditable but is denied under § 911(d)(6).
    """

    elected: bool
    foreign_earned_income_usd: Decimal
    qualifying_test: str
    housing_expenses_usd: Decimal
    location_adjusted_housing_ceiling_usd: Decimal | None
    self_employed: bool
    foreign_tax_paid_on_excluded_income_usd: Decimal


@dataclass(frozen=True)
class USSelfEmploymentInputs2025:
    """26 U.S.C. § 1401 Self-Employment Contributions Act inputs.

    When ``net_se_earnings_usd <= 0`` the SE-tax stage emits zeros.
    ``us_w2_medicare_taxable_wages_usd`` flows into Form 8959 line 1
    (wages subject to U.S. Medicare withholding) and the § 1401(b)(2)
    threshold computation. ``totalization_certificate_present`` records
    whether the taxpayer holds a German Certificate of Coverage under
    the U.S.-Germany Totalization Agreement, which exempts the SE
    earnings from § 1401 OASDI/Medicare. With a certificate present the
    engine fails closed because the certificate path is not modeled.
    """

    net_se_earnings_usd: Decimal
    us_w2_medicare_taxable_wages_usd: Decimal
    totalization_certificate_present: bool


@dataclass(frozen=True)
class USChild2025:
    """Per-child fact block sourced from ``config/children.csv``.

    Authority: 26 U.S.C. § 152(c) (qualifying child) and § 24(h)(7) (SSN
    requirement before due date of return). The legal classification at
    the loader boundary distinguishes between:

    - ``qualifies_for_ctc`` — qualifying child under 17 with a valid SSN
      under § 24(h)(7); eligible for the $2,200 Child Tax Credit
      (§ 24(a) as substituted by § 24(h)(2) post-OBBBA for 2025) and up
      to $1,700 refundable ACTC under § 24(d)(1)(A).
    - ``qualifies_for_odc`` — qualifying relative or qualifying child
      who fails the CTC SSN test (§ 24(h)(7)), but holds a TIN (ITIN or
      SSN); eligible for the $500 Credit for Other Dependents
      (§ 24(h)(4)). NON-refundable.

    For a U.S.-citizen-in-Germany filer, § 152(c)(1)(B) treats months
    living abroad with a U.S.-citizen parent as months "with the
    taxpayer," so ``months_in_us_household`` measures shared residency
    with the taxpayer, NOT months physically inside the United States.

    https://www.law.cornell.edu/uscode/text/26/24
    https://www.law.cornell.edu/uscode/text/26/152
    """

    child_id: str
    name: str
    date_of_birth: str
    ssn: str
    itin: str
    relationship: str
    months_in_us_household: int
    annual_gross_income_usd: Decimal
    disability_gdb: int
    age_at_year_end: int
    qualifies_for_ctc: bool
    qualifies_for_odc: bool


@dataclass(frozen=True)
class USChildrenFacts2025:
    """Aggregate child facts consumed by US25-CTC-AND-ODC.

    ``children`` is the per-child detail; the two count fields are the
    legal aggregates used by the rule (qualifying-child SSN holders for
    CTC vs. ODC dependents). Empty CSV (header-only) yields a zero-count
    instance with an empty tuple — every CTC / ACTC / ODC output is then
    zero by construction.

    Authority: 26 U.S.C. § 24(a) (CTC count), § 24(h)(4) (ODC count),
    § 152(c) and § 152(d) (qualifying child / relative).
    """

    children: tuple[USChild2025, ...]
    children_count_qualifying_for_ctc: int
    children_count_qualifying_for_odc: int


@dataclass(frozen=True)
class USAssessmentInputs2025:
    constants: USTaxConstants2025
    profile: USReturnProfile2025
    capital_facts: USCapitalSourceFacts2025
    ftc_inputs: USFTCInputs2025
    treaty_inputs: USTreatyInputs2025
    feie_inputs: USFEIEInputs2025 = field(
        default_factory=lambda: USFEIEInputs2025(
            elected=False,
            foreign_earned_income_usd=Decimal("0.00"),
            qualifying_test="",
            housing_expenses_usd=Decimal("0.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )
    )
    se_inputs: USSelfEmploymentInputs2025 = field(
        default_factory=lambda: USSelfEmploymentInputs2025(
            net_se_earnings_usd=Decimal("0.00"),
            us_w2_medicare_taxable_wages_usd=Decimal("0.00"),
            totalization_certificate_present=False,
        )
    )
    children_facts: USChildrenFacts2025 = field(
        default_factory=lambda: USChildrenFacts2025(
            children=(),
            children_count_qualifying_for_ctc=0,
            children_count_qualifying_for_odc=0,
        )
    )
    # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): FATCA Form 8938 +
    # FBAR FinCEN 114 determination inputs. The default fails closed
    # (``data_complete=False``) so any workspace that hasn't populated
    # ``foreign-financial-accounts.csv`` surfaces a manual-determination
    # status sheet rather than a silent "not required". Authority:
    # 26 U.S.C. § 6038D / 31 CFR § 1010.350 / CLAUDE.md fail-closed posture.
    fatca_fbar_inputs: "USFATCAFBARInputs2025" = field(
        default_factory=lambda: USFATCAFBARInputs2025(
            filing_status_label="",
            residency_basis="domestic",
            accounts=(),
            data_complete=False,
        )
    )


@dataclass(frozen=True)
class USCapitalAssessment2025:
    short_box_a_usd: Decimal
    short_box_b_usd: Decimal
    short_box_h_usd: Decimal
    short_term_total_usd: Decimal
    long_box_d_usd: Decimal
    long_box_k_usd: Decimal
    capital_gain_distributions_usd: Decimal
    long_term_total_with_cgd_usd: Decimal
    section_1256_total_usd: Decimal
    section_1256_short_term_usd: Decimal
    section_1256_long_term_usd: Decimal
    net_capital_before_1256_usd: Decimal
    net_capital_after_1256_usd: Decimal
    capital_loss_deduction_2025_usd: Decimal
    tentative_capital_loss_carryforward_2026_usd: Decimal
    form_1040_line_7a_usd: Decimal
    digital_asset_transaction_present: bool = False


@dataclass(frozen=True)
class USRegularTaxAssessment2025:
    wages_usd: Decimal
    schedule_1_other_income_usd: Decimal
    adjusted_gross_income_usd: Decimal
    taxable_income_usd: Decimal
    taxable_ordinary_income_usd: Decimal
    ordinary_tax_component_usd: Decimal
    qualified_dividend_tax_component_usd: Decimal
    regular_tax_before_credits_usd: Decimal


@dataclass(frozen=True)
class USFTCAssessment2025:
    total_gross_income_for_ftc_usd: Decimal
    general_standard_deduction_alloc_usd: Decimal
    passive_standard_deduction_alloc_usd: Decimal
    general_taxable_income_for_ftc_usd: Decimal
    passive_taxable_income_for_ftc_usd: Decimal
    general_ftc_limitation_usd: Decimal
    passive_ftc_limitation_usd: Decimal
    current_year_general_foreign_tax_usd: Decimal
    current_year_passive_foreign_tax_usd: Decimal
    passive_available_foreign_tax_usd: Decimal
    general_available_foreign_tax_usd: Decimal
    allowed_general_ftc_usd: Decimal
    allowed_passive_ftc_usd: Decimal
    total_allowed_ftc_usd: Decimal
    regular_tax_after_ftc_usd: Decimal


@dataclass(frozen=True)
class USTreatyResourcingAssessment2025:
    us_source_dividends_usd: Decimal
    us_source_qualified_dividends_usd: Decimal
    us_tax_on_us_source_dividends_usd: Decimal
    treaty_minimum_us_tax_on_us_source_dividends_usd: Decimal
    treaty_resourcing_us_limitation_usd: Decimal
    german_precredit_tax_on_us_source_dividends_usd: Decimal
    german_residence_credit_for_us_tax_usd: Decimal
    worksheet_line_19_maximum_credit_usd: Decimal
    worksheet_line_20c_residual_residence_country_tax_usd: Decimal
    worksheet_line_21_additional_credit_usd: Decimal
    treaty_resourcing_additional_ftc_usd: Decimal
    german_residual_tax_on_us_source_dividends_usd: Decimal
    regular_tax_after_ftc_and_treaty_resourcing_usd: Decimal
    # C7-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): Form 1116 Resourced
    # Line 10 (carryover from prior year) is always 0.00 for the
    # § 904(d)(6) treaty-resourced basket — the basket is created
    # annually by treaty election and § 904(c) carryovers do not cross
    # treaty-basket boundaries. Surfaced as a declared rule output
    # (TREATY25-18) so the renderer transits the I3 contract.
    resourced_basket_carryover_usd: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class USNIITAssessment2025:
    net_investment_income_usd: Decimal
    modified_agi_excess_usd: Decimal
    niit_base_usd: Decimal
    niit_usd: Decimal


@dataclass(frozen=True)
class USAMTAssessment2025:
    """Form 6251 / 26 U.S.C. § 55 result projection.

    Each scalar maps to a specific Form 6251 line (per the 2024-revision
    instructions; the 2025 line numbering is identical):
      - amti_usd                         -> line 4 (AMTI)
      - exemption_usd                    -> line 5 (exemption after phase-out)
      - amti_after_exemption_usd         -> line 6 (line 4 - line 5, floored at 0)
      - preferential_amti_usd            -> § 55(b)(3) preferential income
                                            kept at § 1(h) rates inside AMT
      - tentative_min_tax_usd            -> line 7 (after § 55(b)(3) ordering)
      - amtftc_usd                       -> line 8 (AMTFTC under § 59(a))
      - amt_owed_usd                     -> line 11 (max(0, line 7 - line 8 -
                                            regular tax after FTC))
    """

    amti_usd: Decimal
    preferential_amti_usd: Decimal
    exemption_usd: Decimal
    amti_after_exemption_usd: Decimal
    tentative_min_tax_usd: Decimal
    amtftc_usd: Decimal
    amt_owed_usd: Decimal


def _amt_exemption_for_filing_status_2025(filing_status_label: str) -> Decimal:
    # § 55(d) / Rev. Proc. 2024-40 § 3.11 — filing-status-keyed exemption.
    text = filing_status_label.strip().lower()
    if text == "single":
        return AMT_EXEMPTION_SINGLE_2025_USD
    if text == "married filing jointly":
        return AMT_EXEMPTION_MFJ_2025_USD
    if text == "married filing separately":
        return AMT_EXEMPTION_MFS_2025_USD
    raise NotImplementedError(
        f"AMT exemption not implemented for U.S. filing status {filing_status_label!r}; "
        "expected 'Single', 'Married filing jointly', or 'Married filing separately'."
    )


def _amt_phaseout_start_for_filing_status_2025(filing_status_label: str) -> Decimal:
    # § 55(d)(3) / Rev. Proc. 2024-40 § 3.11 — filing-status-keyed phase-out start.
    text = filing_status_label.strip().lower()
    if text == "single":
        return AMT_PHASEOUT_START_SINGLE_2025_USD
    if text == "married filing jointly":
        return AMT_PHASEOUT_START_MFJ_2025_USD
    if text == "married filing separately":
        return AMT_PHASEOUT_START_MFS_2025_USD
    raise NotImplementedError(
        f"AMT phase-out start not implemented for U.S. filing status {filing_status_label!r}."
    )


def _amt_rate_break_for_filing_status_2025(filing_status_label: str) -> Decimal:
    # § 55(b)(1)(A)(ii) — 26%/28% rate break is halved for MFS (§ 55(b)(1)(A)(ii)(II)).
    text = filing_status_label.strip().lower()
    if text == "married filing separately":
        return AMT_RATE_BREAK_MFS_2025_USD
    if text in ("single", "married filing jointly"):
        return AMT_RATE_BREAK_2025_USD
    raise NotImplementedError(
        f"AMT 26/28 break not implemented for U.S. filing status {filing_status_label!r}."
    )


def amt_exemption_after_phaseout_2025(
    *,
    amti_usd: Decimal,
    filing_status_label: str,
) -> Decimal:
    # § 55(d)(3): the AMT exemption is reduced by 25 cents per dollar of AMTI
    # above the filing-status phase-out start, floored at zero.
    # https://www.law.cornell.edu/uscode/text/26/55
    _require_non_negative(amti_usd, label="amti_usd")
    base = _amt_exemption_for_filing_status_2025(filing_status_label)
    threshold = _amt_phaseout_start_for_filing_status_2025(filing_status_label)
    if amti_usd <= threshold:
        return round_cents(base)
    reduction = (amti_usd - threshold) * AMT_PHASEOUT_RATE
    reduced = base - reduction
    if reduced <= ZERO_USD:
        return ZERO_USD
    return round_cents(reduced)


def amt_tentative_minimum_tax_2025(
    *,
    amti_after_exemption_usd: Decimal,
    preferential_amti_usd: Decimal,
    filing_status_label: str,
    constants: USTaxConstants2025,
) -> Decimal:
    # § 55(b)(1) tentative minimum tax = 26% × min(AMTI_excess, break) + 28% ×
    # max(0, AMTI_excess - break). § 55(b)(3) preserves § 1(h) preferential
    # rates on long-term capital gain and qualified dividends inside AMT, so
    # the tentative minimum splits the AMTI base into ordinary AMTI and
    # preferential AMTI, taxes the ordinary portion at 26/28, and runs a
    # § 1(h)-style QDCGTW on the preferential portion using the AMTI base
    # (the same § 1(h)(1) ceilings that apply for regular tax).
    # https://www.law.cornell.edu/uscode/text/26/55
    # https://www.law.cornell.edu/uscode/text/26/1
    _require_non_negative(amti_after_exemption_usd, label="amti_after_exemption_usd")
    _require_non_negative(preferential_amti_usd, label="preferential_amti_usd")
    if preferential_amti_usd > amti_after_exemption_usd:
        raise ValueError(
            "preferential_amti_usd cannot exceed amti_after_exemption_usd; "
            "the preferential portion is bounded by post-exemption AMTI under § 55(b)(3)."
        )
    if amti_after_exemption_usd == ZERO_USD:
        return ZERO_USD
    rate_break = _amt_rate_break_for_filing_status_2025(filing_status_label)

    # Ordinary AMTI taxed at 26/28.
    ordinary_amti = amti_after_exemption_usd - preferential_amti_usd
    ordinary_amti_low_band = min(ordinary_amti, rate_break)
    ordinary_amti_high_band = max(ZERO_USD, ordinary_amti - rate_break)
    ordinary_tax = (
        ordinary_amti_low_band * AMT_RATE_LOW
        + ordinary_amti_high_band * AMT_RATE_HIGH
    )

    # § 55(b)(3) preferential portion: rerun the § 1(h) qualified-dividend /
    # capital-gain worksheet using the AMTI base. The 26%/28% schedule plays
    # the role of the § 1 ordinary schedule. The same § 1(h)(1) zero / 15% /
    # 20% ceilings apply per Form 6251 instructions and Pub. 550.
    # The preferential AMTI is the long-term capital gain + qualified dividends
    # subset of AMTI (capped at amti_after_exemption_usd).
    if preferential_amti_usd == ZERO_USD:
        preferential_tax = ZERO_USD
    else:
        zero_ceiling = constants.qualified_dividend_zero_rate_ceiling_2025_usd
        fifteen_ceiling = constants.qualified_dividend_fifteen_rate_ceiling_2025_usd
        # The QDCGTW first allocates ordinary income to the zero-rate band.
        ordinary_band_used = min(ordinary_amti, zero_ceiling)
        zero_band_room = max(ZERO_USD, zero_ceiling - ordinary_band_used)
        preferential_zero = min(preferential_amti_usd, zero_band_room)
        preferential_after_zero = preferential_amti_usd - preferential_zero
        # Fifteen-percent room: the 15% bracket runs from zero_ceiling up
        # through fifteen_ceiling (after ordinary income is allocated).
        ordinary_plus_zero = ordinary_amti + preferential_zero
        fifteen_band_room = max(ZERO_USD, fifteen_ceiling - ordinary_plus_zero)
        preferential_fifteen = min(preferential_after_zero, fifteen_band_room)
        preferential_twenty = preferential_after_zero - preferential_fifteen
        preferential_tax = (
            preferential_zero * Decimal("0.00")
            + preferential_fifteen * QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE
            + preferential_twenty * QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE
        )

    # § 55(b)(1) requires the tentative minimum to be the lesser of (a) the
    # 26/28 schedule applied to all AMTI excess and (b) the preferential
    # decomposition. This mirrors Form 6251 Part III line 40.
    flat_tax = (
        min(amti_after_exemption_usd, rate_break) * AMT_RATE_LOW
        + max(ZERO_USD, amti_after_exemption_usd - rate_break) * AMT_RATE_HIGH
    )
    return round_cents(min(ordinary_tax + preferential_tax, flat_tax))


def amt_owed_2025(
    *,
    tentative_min_tax_usd: Decimal,
    amtftc_usd: Decimal,
    regular_tax_after_ftc_usd: Decimal,
) -> Decimal:
    # § 55(a): AMT = max(0, tentative_min_tax - AMTFTC - regular_tax_after_FTC).
    # The credit baseline for the regular-tax side of the comparison is
    # regular tax less its allowed FTC (Form 6251 line 9 / line 10 ordering).
    # https://www.law.cornell.edu/uscode/text/26/55
    _require_non_negative(tentative_min_tax_usd, label="tentative_min_tax_usd")
    _require_non_negative(amtftc_usd, label="amtftc_usd")
    _require_non_negative(regular_tax_after_ftc_usd, label="regular_tax_after_ftc_usd")
    raw = tentative_min_tax_usd - amtftc_usd - regular_tax_after_ftc_usd
    if raw <= ZERO_USD:
        return ZERO_USD
    return round_cents(raw)


@dataclass(frozen=True)
class USLawStage2025:
    step: str
    amount: Decimal
    note: str
    legal_reference: str
    authority_url: str
    step_type: str = "mechanical"
    precision_note: str = ""


@dataclass(frozen=True)
class USOverallAssessment2025:
    capital: USCapitalAssessment2025
    regular_tax: USRegularTaxAssessment2025
    ftc: USFTCAssessment2025
    treaty_resourcing: USTreatyResourcingAssessment2025
    niit: USNIITAssessment2025
    # 26 U.S.C. §§ 55, 56, 59 + Form 6251 — added under F-US-1. ``amt`` is the
    # baseline (no treaty re-sourcing) AMT computation; ``amt_with_treaty_resourcing``
    # uses the post-Pub.514 allowed FTC as the regular-tax-after-FTC baseline.
    amt: USAMTAssessment2025
    amt_with_treaty_resourcing: USAMTAssessment2025
    total_tax_usd: Decimal
    total_tax_with_treaty_resourcing_usd: Decimal
    refund_if_positive_else_balance_due_usd: Decimal
    refund_if_positive_else_balance_due_with_treaty_resourcing_usd: Decimal
    law_order_stages: tuple[USLawStage2025, ...] = ()


def validate_supported_us_filing_positions_2025(inputs: USAssessmentInputs2025) -> None:
    # Fix: keep filing-policy switches out of the law math.
    # The 2025 U.S. core currently implements one explicit FTC posture: documented positive
    # income in the denominator and wage-share allocation of joint German wage tax. Any other
    # position must fail loudly until implemented, rather than silently producing a different
    # "law" result.
    if not inputs.ftc_inputs.conservative_positive_income_only:
        raise NotImplementedError(
            "Only the documented positive-income FTC denominator posture is implemented for U.S. 2025."
        )
    # Workstream 3 — 26 U.S.C. § 905(a) paid-basis FTC posture. Accrued
    # (§ 901 default) and cash-basis paid-when-paid (§ 905(a) election)
    # are both supported postures; the timing posture is recorded on
    # ``USReturnProfile2025.accrued_basis_ftc`` and consumed by the FTC
    # chain. The legal arithmetic uses available foreign tax (current +
    # carryover); cash-basis filers count only foreign tax actually
    # paid in the calendar year, while accrued-basis filers count tax
    # accrued for the tax year. Carryforward/carryback rules differ
    # per § 904(c). https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905
    if not inputs.ftc_inputs.allocate_joint_german_tax_by_wage_share:
        raise NotImplementedError(
            "Only wage-share allocation of joint German wage-side tax is implemented for U.S. 2025."
        )


def validate_us_assessment_source_amounts_2025(inputs: USAssessmentInputs2025) -> None:
    # 26 U.S.C. §§ 61/63 include income from legally possible source facts, §§
    # 901/904 credit only actual foreign taxes, § 1211 consumes computed gains/losses,
    # and § 1411 taxes a non-negative NIIT base. Validate source amounts before the
    # ordered law sequence; net gain/loss fields remain allowed to be negative.
    constants = inputs.constants
    for label, value in (
        ("eur_per_usd_yearly_average_2025", constants.eur_per_usd_yearly_average_2025),
        ("standard_deduction_2025_usd", constants.standard_deduction_2025_usd),
        ("capital_loss_limit_usd", constants.capital_loss_limit_usd),
        ("niit_threshold_usd", constants.niit_threshold_usd),
        ("qualified_dividend_zero_rate_ceiling_2025_usd", constants.qualified_dividend_zero_rate_ceiling_2025_usd),
        ("qualified_dividend_fifteen_rate_ceiling_2025_usd", constants.qualified_dividend_fifteen_rate_ceiling_2025_usd),
        ("tax_bracket_10_ceiling_2025_usd", constants.tax_bracket_10_ceiling_2025_usd),
        ("tax_bracket_12_ceiling_2025_usd", constants.tax_bracket_12_ceiling_2025_usd),
        ("tax_bracket_22_ceiling_2025_usd", constants.tax_bracket_22_ceiling_2025_usd),
        ("tax_bracket_24_ceiling_2025_usd", constants.tax_bracket_24_ceiling_2025_usd),
        ("tax_bracket_32_ceiling_2025_usd", constants.tax_bracket_32_ceiling_2025_usd),
        ("tax_bracket_35_ceiling_2025_usd", constants.tax_bracket_35_ceiling_2025_usd),
    ):
        _require_non_negative(value, label=label)
    _require_positive(constants.eur_per_usd_yearly_average_2025, label="eur_per_usd_yearly_average_2025")

    facts = inputs.capital_facts
    for label, value in (
        ("ordinary_dividends_usd", facts.ordinary_dividends_usd),
        ("qualified_dividends_usd", facts.qualified_dividends_usd),
        ("capital_gain_distributions_usd", facts.capital_gain_distributions_usd),
        ("nondividend_distributions_usd", facts.nondividend_distributions_usd),
        ("foreign_tax_paid_usd", facts.foreign_tax_paid_usd),
        ("interest_income_usd", facts.interest_income_usd),
        ("substitute_payments_usd", facts.substitute_payments_usd),
        ("staking_income_usd", facts.staking_income_usd),
        ("estimated_payment_2025_usd", facts.estimated_payment_2025_usd),
        ("passive_ftc_carryover_2024_usd", facts.passive_ftc_carryover_2024_usd),
        ("general_ftc_carryover_2024_usd", facts.general_ftc_carryover_2024_usd),
        ("german_2024_redetermination_paid_2025_eur", facts.german_2024_redetermination_paid_2025_eur),
        ("coinbase_short_with_basis_proceeds_usd", facts.coinbase_short_with_basis_proceeds_usd),
        ("coinbase_short_with_basis_basis_usd", facts.coinbase_short_with_basis_basis_usd),
        ("coinbase_short_unknown_proceeds_usd", facts.coinbase_short_unknown_proceeds_usd),
        ("coinbase_short_unknown_basis_reconstructed_usd", facts.coinbase_short_unknown_basis_reconstructed_usd),
        ("coinbase_long_with_basis_proceeds_usd", facts.coinbase_long_with_basis_proceeds_usd),
        ("coinbase_long_with_basis_basis_usd", facts.coinbase_long_with_basis_basis_usd),
    ):
        _require_non_negative(value, label=label)

    ftc = inputs.ftc_inputs
    for label, value in (
        ("taxpayer_gross_wages_eur", ftc.taxpayer_gross_wages_eur),
        ("spouse_gross_wages_eur", ftc.spouse_gross_wages_eur),
        ("joint_wage_side_tax_eur", ftc.joint_wage_side_tax_eur),
        ("foreign_source_passive_dividends_usd", ftc.foreign_source_passive_dividends_usd),
        ("foreign_source_qualified_dividends_usd", ftc.foreign_source_qualified_dividends_usd),
        ("foreign_source_net_capital_gain_usd", ftc.foreign_source_net_capital_gain_usd),
        ("known_positive_short_capital_gain_usd", ftc.known_positive_short_capital_gain_usd),
        ("known_positive_long_capital_gain_usd", ftc.known_positive_long_capital_gain_usd),
    ):
        _require_non_negative(value, label=label)

    validate_treaty_resourcing_inputs_2025(
        ordinary_dividends_usd=facts.ordinary_dividends_usd,
        qualified_dividends_usd=facts.qualified_dividends_usd,
        foreign_source_passive_dividends_usd=ftc.foreign_source_passive_dividends_usd,
        foreign_source_qualified_dividends_usd=ftc.foreign_source_qualified_dividends_usd,
        treaty_inputs=inputs.treaty_inputs,
    )


def validate_treaty_resourcing_dividend_split_2025(
    *,
    computed_us_source_dividends_usd: Decimal,
    treaty_inputs: USTreatyInputs2025,
) -> None:
    # Fix: worksheet lines 12/16 and 17/21 must refer to the same U.S.-source dividend base.
    # If the manual German treaty split stops reconciling to the computed U.S.-source dividend
    # amount, the additional FTC worksheet becomes internally inconsistent.
    split_total = round_cents(
        treaty_inputs.us_source_direct_equity_dividends_usd
        + treaty_inputs.us_source_equity_fund_dividends_usd
        + treaty_inputs.us_source_non_equity_fund_dividends_usd
    )
    if split_total != round_cents(computed_us_source_dividends_usd):
        raise ValueError(
            "Treaty dividend split must reconcile to the computed U.S.-source dividend total."
        )
    item_total = round_cents(sum((item.gross_dividend_usd for item in treaty_inputs.us_treaty_dividend_items), ZERO_USD))
    if item_total != round_cents(computed_us_source_dividends_usd):
        # Pub. 514 lines 1/8/12/16 must be the same U.S.-source dividend stack used
        # for lines 17/18. The U.S. side therefore needs item-level coverage rather
        # than only an aggregate amount (https://www.irs.gov/publications/p514).
        raise ValueError("U.S. treaty dividend item coverage must reconcile to the computed U.S.-source dividend total.")


def validate_treaty_resourcing_inputs_2025(
    *,
    ordinary_dividends_usd: Decimal,
    qualified_dividends_usd: Decimal,
    foreign_source_passive_dividends_usd: Decimal,
    foreign_source_qualified_dividends_usd: Decimal,
    treaty_inputs: USTreatyInputs2025,
) -> None:
    validate_us_source_split_inputs_2025(
        ordinary_dividends_usd=ordinary_dividends_usd,
        qualified_dividends_usd=qualified_dividends_usd,
        foreign_source_passive_dividends_usd=foreign_source_passive_dividends_usd,
        foreign_source_qualified_dividends_usd=foreign_source_qualified_dividends_usd,
    )
    for label, value in (
        ("us_source_direct_equity_dividends_usd", treaty_inputs.us_source_direct_equity_dividends_usd),
        ("us_source_equity_fund_dividends_usd", treaty_inputs.us_source_equity_fund_dividends_usd),
        ("us_source_non_equity_fund_dividends_usd", treaty_inputs.us_source_non_equity_fund_dividends_usd),
    ):
        _require_non_negative(value, label=label)
    for item in treaty_inputs.us_treaty_dividend_items:
        if not str(item.item_id).strip():
            raise ValueError("U.S. treaty dividend item_id is required.")
        if str(item.treaty_bucket).strip() not in {"direct_equity", "equity_fund", "non_equity_fund"}:
            raise ValueError(f"Unsupported U.S. treaty dividend bucket: {item.treaty_bucket!r}")
        _require_non_negative(item.gross_dividend_usd, label="gross_dividend_usd")
    for item in treaty_inputs.germany_treaty_dividend_items:
        if not str(item.item_id).strip():
            raise ValueError("Germany treaty dividend packet item_id is required.")
        for label, value in (
            ("gross_dividend_eur", item.gross_dividend_eur),
            ("gross_dividend_usd", item.gross_dividend_usd),
            ("german_taxable_dividend_eur", item.german_taxable_dividend_eur),
            ("article_10_source_tax_ceiling_usd", item.article_10_source_tax_ceiling_usd),
            (
                "german_precredit_tax_on_us_source_dividend_usd",
                item.german_precredit_tax_on_us_source_dividend_usd,
            ),
            ("german_residence_credit_for_us_tax_usd", item.german_residence_credit_for_us_tax_usd),
        ):
            _require_non_negative(value, label=label)
    if treaty_inputs.german_precredit_tax_on_us_source_dividends_usd is not None:
        _require_non_negative(
            treaty_inputs.german_precredit_tax_on_us_source_dividends_usd,
            label="german_precredit_tax_on_us_source_dividends_usd",
        )
    if treaty_inputs.german_residence_credit_for_us_tax_usd is not None:
        _require_non_negative(
            treaty_inputs.german_residence_credit_for_us_tax_usd,
            label="german_residence_credit_for_us_tax_usd",
        )
    germany_output_fields = {
        "germany_treaty_us_source_dividend_gross_usd": treaty_inputs.germany_treaty_us_source_dividend_gross_usd,
        "germany_treaty_us_source_dividend_allowed_us_tax_usd": (
            treaty_inputs.germany_treaty_us_source_dividend_allowed_us_tax_usd
        ),
        "german_precredit_tax_on_us_source_dividends_usd": (
            treaty_inputs.german_precredit_tax_on_us_source_dividends_usd
        ),
        "german_residence_credit_for_us_tax_usd": treaty_inputs.german_residence_credit_for_us_tax_usd,
    }
    present_germany_outputs = [label for label, value in germany_output_fields.items() if value is not None]
    if present_germany_outputs and len(present_germany_outputs) != len(germany_output_fields):
        raise ValueError(
            "Incomplete Germany treaty dividend outputs: "
            + ", ".join(germany_output_fields.keys())
            + " must all be present or all be absent."
        )
    for label, value in germany_output_fields.items():
        if value is not None:
            _require_non_negative(value, label=label)


def validate_us_source_split_inputs_2025(
    *,
    ordinary_dividends_usd: Decimal,
    qualified_dividends_usd: Decimal,
    foreign_source_passive_dividends_usd: Decimal,
    foreign_source_qualified_dividends_usd: Decimal,
) -> None:
    # Form 1116 and Publication 514 source splits are core FTC facts, not just treaty
    # facts. Validate them before both the base 26 U.S.C. § 904 limitation and the
    # optional treaty-resourcing branch so impossible U.S.-source residuals fail closed.
    _require_non_negative(ordinary_dividends_usd, label="ordinary_dividends_usd")
    _require_non_negative(qualified_dividends_usd, label="qualified_dividends_usd")
    _require_non_negative(
        foreign_source_passive_dividends_usd,
        label="foreign_source_passive_dividends_usd",
    )
    _require_non_negative(
        foreign_source_qualified_dividends_usd,
        label="foreign_source_qualified_dividends_usd",
    )
    if qualified_dividends_usd > ordinary_dividends_usd:
        # 26 U.S.C. § 1(h)(11) preferential qualified dividends are a subset of
        # dividend gross income under 26 U.S.C. § 61(a)(7); Form 1040 line 3a is
        # therefore a subset of line 3b. Source: https://www.irs.gov/instructions/i1040gi.
        raise ValueError("Qualified dividends cannot exceed ordinary dividends.")
    if foreign_source_passive_dividends_usd > ordinary_dividends_usd:
        raise ValueError("U.S.-source dividends cannot be negative.")
    if foreign_source_qualified_dividends_usd > qualified_dividends_usd:
        raise ValueError("U.S.-source qualified dividends cannot be negative.")
    if foreign_source_qualified_dividends_usd > foreign_source_passive_dividends_usd:
        raise ValueError("Foreign-source qualified dividends cannot exceed foreign-source passive dividends.")


def validate_germany_treaty_dividend_coverage_2025(
    *,
    us_source_dividends_usd: Decimal,
    treaty_allowed_us_tax_at_source_usd: Decimal,
    treaty_inputs: USTreatyInputs2025,
) -> None:
    # IRS Publication 514's additional-credit worksheet uses the same U.S.-source
    # income on lines 1/8/12/16 and the residence-country tax/credit on lines
    # 17/18 (https://www.irs.gov/publications/p514). DBA-USA Art. 23 is therefore
    # a cross-country coverage invariant: the Germany core output must identify
    # the same dividend stack before the U.S. core may claim treaty re-sourcing
    # (https://www.irs.gov/pub/irs-trty/germtech.pdf).
    if not treaty_inputs.use_treaty_resourcing or us_source_dividends_usd == ZERO_USD:
        return
    if (
        treaty_inputs.germany_treaty_us_source_dividend_gross_usd is None
        or treaty_inputs.germany_treaty_us_source_dividend_allowed_us_tax_usd is None
        or treaty_inputs.german_precredit_tax_on_us_source_dividends_usd is None
        or treaty_inputs.german_residence_credit_for_us_tax_usd is None
    ):
        raise ValueError(
            "Germany treaty dividend packet outputs are required when treaty re-sourcing is enabled "
            "for positive U.S.-source dividends."
        )
    if treaty_inputs.germany_treaty_us_source_dividend_gross_usd != us_source_dividends_usd:
        raise ValueError(
            "Germany treaty dividend gross must match the computed U.S.-source dividend total "
            "for Publication 514 treaty re-sourcing."
        )
    us_item_ids = {str(item.item_id).strip() for item in treaty_inputs.us_treaty_dividend_items}
    germany_item_ids = {str(item.item_id).strip() for item in treaty_inputs.germany_treaty_dividend_items}
    if not us_item_ids or not germany_item_ids:
        raise ValueError("Treaty re-sourcing requires item-level U.S. and Germany dividend coverage.")
    if us_item_ids != germany_item_ids:
        # DBA-USA Art. 23 and Pub. 514 lines 17/18 require the residence-country
        # tax/credit for the same income stack used on the U.S. worksheet. Compare
        # item identity first; amount equality alone can hide FX or source-bucket drift.
        raise ValueError("Treaty dividend item coverage mismatch between U.S. and Germany packets.")
    germany_item_gross_total = round_cents(
        sum((item.gross_dividend_usd for item in treaty_inputs.germany_treaty_dividend_items), ZERO_USD)
    )
    if germany_item_gross_total != us_source_dividends_usd:
        raise ValueError("Germany treaty dividend packet item gross must reconcile to the U.S.-source dividend total.")
    if treaty_inputs.germany_treaty_us_source_dividend_allowed_us_tax_usd > treaty_allowed_us_tax_at_source_usd:
        raise ValueError(
            "Germany treaty allowed U.S. tax cannot exceed the treaty source-country tax ceiling "
            "used on Publication 514 line 16."
        )
    if (
        treaty_inputs.german_residence_credit_for_us_tax_usd
        > treaty_inputs.germany_treaty_us_source_dividend_allowed_us_tax_usd
    ):
        raise ValueError(
            "Germany residence-country credit cannot exceed Germany's treaty-allowed U.S. tax "
            "for the matched dividend stack."
        )


def section_1256_split_2025(total_usd: Decimal) -> tuple[Decimal, Decimal]:
    # 26 U.S.C. § 1256(a)(3) applies the statutory 40/60 character split.
    short_term = round_cents(total_usd * SECTION_1256_SHORT_RATIO)
    long_term = round_cents(total_usd * SECTION_1256_LONG_RATIO)
    return short_term, long_term


def compute_capital_assessment_2025(
    facts: USCapitalSourceFacts2025,
    *,
    capital_loss_limit_usd: Decimal = MFS_CAPITAL_LOSS_LIMIT_USD,
) -> USCapitalAssessment2025:
    # Form 8949 / Schedule D bucket assembly follows the documented broker categories and
    # 26 U.S.C. §§ 1211-1212 apply the annual MFS capital-loss limit and carryforward.
    short_box_a = round_cents(facts.schwab_short_box_a_gain_usd + facts.jpm_short_type_a_gain_usd)
    short_box_b = round_cents(facts.schwab_short_box_b_gain_usd)
    short_box_h = round_cents(
        facts.coinbase_short_with_basis_proceeds_usd
        - facts.coinbase_short_with_basis_basis_usd
        + facts.coinbase_short_unknown_proceeds_usd
        - facts.coinbase_short_unknown_basis_reconstructed_usd
    )
    long_box_d = round_cents(facts.schwab_long_box_d_gain_usd)
    long_box_k = round_cents(facts.coinbase_long_with_basis_proceeds_usd - facts.coinbase_long_with_basis_basis_usd)
    short_term_total = round_cents(short_box_a + short_box_b + short_box_h)
    long_term_total_with_cgd = round_cents(long_box_d + long_box_k + facts.capital_gain_distributions_usd)
    net_capital_before_1256 = round_cents(short_term_total + long_term_total_with_cgd)
    net_capital_after_1256 = round_cents(net_capital_before_1256 + facts.schwab_section_1256_total_usd)
    _require_non_negative(capital_loss_limit_usd, label="capital_loss_limit_usd")
    if net_capital_after_1256 < 0:
        capital_loss_deduction = round_cents(min(capital_loss_limit_usd, -net_capital_after_1256))
        capital_loss_carryforward = round_cents(-net_capital_after_1256 - capital_loss_deduction)
        form_1040_line_7a = round_cents(-capital_loss_deduction)
    else:
        capital_loss_deduction = Decimal("0.00")
        capital_loss_carryforward = Decimal("0.00")
        form_1040_line_7a = round_cents(net_capital_after_1256)
    section_1256_short_term, section_1256_long_term = section_1256_split_2025(
        facts.schwab_section_1256_total_usd
    )
    digital_asset_transaction_present = any(
        value != ZERO_USD
        for value in (
            facts.coinbase_short_with_basis_proceeds_usd,
            facts.coinbase_short_with_basis_basis_usd,
            facts.coinbase_short_unknown_proceeds_usd,
            facts.coinbase_short_unknown_basis_reconstructed_usd,
            facts.coinbase_long_with_basis_proceeds_usd,
            facts.coinbase_long_with_basis_basis_usd,
        )
    )
    return USCapitalAssessment2025(
        short_box_a_usd=short_box_a,
        short_box_b_usd=short_box_b,
        short_box_h_usd=short_box_h,
        short_term_total_usd=short_term_total,
        long_box_d_usd=long_box_d,
        long_box_k_usd=long_box_k,
        capital_gain_distributions_usd=round_cents(facts.capital_gain_distributions_usd),
        long_term_total_with_cgd_usd=long_term_total_with_cgd,
        section_1256_total_usd=round_cents(facts.schwab_section_1256_total_usd),
        section_1256_short_term_usd=section_1256_short_term,
        section_1256_long_term_usd=section_1256_long_term,
        net_capital_before_1256_usd=net_capital_before_1256,
        net_capital_after_1256_usd=net_capital_after_1256,
        capital_loss_deduction_2025_usd=capital_loss_deduction,
        tentative_capital_loss_carryforward_2026_usd=capital_loss_carryforward,
        form_1040_line_7a_usd=form_1040_line_7a,
        digital_asset_transaction_present=digital_asset_transaction_present,
    )


def net_capital_gain_for_preferential_tax_2025(capital: USCapitalAssessment2025) -> Decimal:
    # IRS Form 1040 line-16 Qualified Dividends and Capital Gain Tax Worksheet line 3 uses
    # the smaller of Schedule D lines 15 and 16, or zero if either line is blank or a loss.
    schedule_d_line_15 = round_cents(capital.long_term_total_with_cgd_usd + capital.section_1256_long_term_usd)
    schedule_d_line_16 = capital.net_capital_after_1256_usd
    if schedule_d_line_15 <= ZERO_USD or schedule_d_line_16 <= ZERO_USD:
        return ZERO_USD
    return round_cents(min(schedule_d_line_15, schedule_d_line_16))


def wages_usd_2025(gross_wages_eur: Decimal, eur_per_usd_yearly_average_2025: Decimal) -> Decimal:
    # IRS yearly-average FX guidance is used for annual foreign wage translation in the saved model.
    _require_non_negative(gross_wages_eur, label="gross_wages_eur")
    _require_positive(eur_per_usd_yearly_average_2025, label="eur_per_usd_yearly_average_2025")
    return round_cents(gross_wages_eur / eur_per_usd_yearly_average_2025)


def _tax_table_lookup_income_2025(taxable_ordinary_income: Decimal) -> Decimal:
    # IRS Form 1040 line-16 instructions require the Tax Table below $100,000.
    # The table's early rows are not uniform $50 buckets: 0-5 is zero-tax, 5-25
    # uses $10 rows, 25-3,000 uses $25 rows, and 3,000-100,000 uses $50 rows.
    if taxable_ordinary_income < Decimal("5.00"):
        return ZERO_USD
    if taxable_ordinary_income < Decimal("25.00"):
        row_start = Decimal("5.00") + (
            (taxable_ordinary_income - Decimal("5.00")) / Decimal("10.00")
        ).to_integral_value(rounding=ROUND_FLOOR) * Decimal("10.00")
        return row_start + Decimal("5.00")
    if taxable_ordinary_income < Decimal("3000.00"):
        row_start = Decimal("25.00") + (
            (taxable_ordinary_income - Decimal("25.00")) / Decimal("25.00")
        ).to_integral_value(rounding=ROUND_FLOOR) * Decimal("25.00")
        return row_start + Decimal("12.50")
    row_start = Decimal("3000.00") + (
        (taxable_ordinary_income - Decimal("3000.00")) / Decimal("50.00")
    ).to_integral_value(rounding=ROUND_FLOOR) * Decimal("50.00")
    return row_start + Decimal("25.00")


def adjusted_gross_income_2025(
    *,
    wages_usd: Decimal,
    ordinary_dividends_usd: Decimal,
    interest_income_usd: Decimal,
    schedule_1_other_income_usd: Decimal,
    form_1040_line_7a_usd: Decimal,
    one_half_se_tax_deduction_usd: Decimal = ZERO_USD,
) -> Decimal:
    # 26 U.S.C. § 61 defines gross income and Form 1040 line 11 carries AGI
    # after the line-7a capital result and Schedule 1 income are reflected.
    # F-C1 — 26 U.S.C. § 164(f)(1) lets the taxpayer deduct ONE-HALF of the
    # § 1401 SE tax (§ 1401(a) OASDI + § 1401(b)(1) Medicare; the
    # § 1401(b)(2) Additional Medicare is NOT § 164(f) deductible) as an
    # above-the-line adjustment, lands on Schedule 1 line 15 and reduces
    # AGI on Form 1040 line 10. ``one_half_se_tax_deduction_usd`` must be
    # the cent-rounded one-half of ``us.stage.se_tax.se_tax_usd``; the
    # caller (us25_07_agi) computes and rounds it before passing it in.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164
    _require_non_negative(
        one_half_se_tax_deduction_usd, label="one_half_se_tax_deduction_usd"
    )
    return (
        wages_usd
        + ordinary_dividends_usd
        + interest_income_usd
        + schedule_1_other_income_usd
        + form_1040_line_7a_usd
        - one_half_se_tax_deduction_usd
    )


def taxable_income_2025(
    adjusted_gross_income_usd: Decimal,
    standard_deduction_2025_usd: Decimal,
) -> Decimal:
    # 26 U.S.C. § 63 defines taxable income after the standard deduction.
    return max(Decimal("0.00"), adjusted_gross_income_usd - standard_deduction_2025_usd)


def _tax_from_ordinary_brackets_2025(
    taxable_ordinary_income: Decimal,
    constants: USTaxConstants2025,
) -> Decimal:
    thresholds = [
        Decimal("0.00"),
        constants.tax_bracket_10_ceiling_2025_usd,
        constants.tax_bracket_12_ceiling_2025_usd,
        constants.tax_bracket_22_ceiling_2025_usd,
        constants.tax_bracket_24_ceiling_2025_usd,
        constants.tax_bracket_32_ceiling_2025_usd,
        constants.tax_bracket_35_ceiling_2025_usd,
    ]
    rates = [Decimal("0.10"), Decimal("0.12"), Decimal("0.22"), Decimal("0.24"), Decimal("0.32"), Decimal("0.35"), Decimal("0.37")]
    base_taxes = [Decimal("0.00")]
    cumulative = Decimal("0.00")
    for idx, rate in enumerate(rates[:-1]):
        bracket_width = thresholds[idx + 1] - thresholds[idx]
        cumulative += bracket_width * rate
        base_taxes.append(cumulative)
    for idx, rate in enumerate(rates):
        low = thresholds[idx]
        high = thresholds[idx + 1] if idx + 1 < len(thresholds) else None
        if high is None or taxable_ordinary_income <= high:
            return base_taxes[idx] + (taxable_ordinary_income - low) * rate
    raise RuntimeError("unreachable 2025 tax schedule state")


def tax_from_schedule_y2_2025(
    taxable_ordinary_income: Decimal,
    constants: USTaxConstants2025,
) -> Decimal:
    # 26 U.S.C. § 1 imposes the ordinary-income tax. Form 1040 line-16 instructions require
    # the Tax Table for taxable income below $100,000; $100,000+ uses the computation worksheet.
    _require_non_negative(taxable_ordinary_income, label="taxable_ordinary_income")
    if taxable_ordinary_income == ZERO_USD:
        return ZERO_USD
    if taxable_ordinary_income < Decimal("100000.00"):
        table_income = _tax_table_lookup_income_2025(taxable_ordinary_income)
        table_tax = _tax_from_ordinary_brackets_2025(table_income, constants)
        return table_tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(USD_CENT)
    return _tax_from_ordinary_brackets_2025(taxable_ordinary_income, constants)


def tax_from_schedule_y2_2025_mfs(
    taxable_ordinary_income: Decimal,
    constants: USTaxConstants2025,
) -> Decimal:
    return tax_from_schedule_y2_2025(taxable_ordinary_income, constants)


def regular_tax_2025(
    taxable_income_usd: Decimal,
    qualified_dividends_usd: Decimal,
    constants: USTaxConstants2025,
    *,
    net_capital_gain_usd: Decimal = ZERO_USD,
) -> USRegularTaxAssessment2025:
    # 26 U.S.C. § 1(h) gives qualified dividends and net capital gain the capital-gain
    # rate schedule. This follows the 2025 Form 1040 line-16 Qualified Dividends and
    # Capital Gain Tax Worksheet for the currently selected filing-status constants.
    _require_non_negative(taxable_income_usd, label="taxable_income_usd")
    _require_non_negative(qualified_dividends_usd, label="qualified_dividends_usd")
    _require_non_negative(net_capital_gain_usd, label="net_capital_gain_usd")

    line_1_taxable_income = taxable_income_usd
    line_2_qualified_dividends = qualified_dividends_usd
    line_3_net_capital_gain = net_capital_gain_usd
    line_4_preferential_income = round_cents(line_2_qualified_dividends + line_3_net_capital_gain)
    line_5_taxable_ordinary_income = round_cents(
        max(ZERO_USD, line_1_taxable_income - line_4_preferential_income)
    )
    line_7_zero_ceiling = min(
        line_1_taxable_income,
        constants.qualified_dividend_zero_rate_ceiling_2025_usd,
    )
    line_8_ordinary_income_in_zero_band = min(line_5_taxable_ordinary_income, line_7_zero_ceiling)
    line_9_zero_rate_income = round_cents(line_7_zero_ceiling - line_8_ordinary_income_in_zero_band)
    line_10_preferential_income_limited = min(line_1_taxable_income, line_4_preferential_income)
    line_12_preferential_after_zero = round_cents(line_10_preferential_income_limited - line_9_zero_rate_income)
    line_14_fifteen_ceiling = min(
        line_1_taxable_income,
        constants.qualified_dividend_fifteen_rate_ceiling_2025_usd,
    )
    line_15_ord_plus_zero = round_cents(line_5_taxable_ordinary_income + line_9_zero_rate_income)
    line_16_fifteen_rate_room = round_cents(max(ZERO_USD, line_14_fifteen_ceiling - line_15_ord_plus_zero))
    line_17_fifteen_rate_income = min(line_12_preferential_after_zero, line_16_fifteen_rate_room)
    line_18_fifteen_rate_tax = round_cents(line_17_fifteen_rate_income * QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE)
    line_19_zero_and_fifteen = round_cents(line_9_zero_rate_income + line_17_fifteen_rate_income)
    line_20_twenty_rate_income = round_cents(line_10_preferential_income_limited - line_19_zero_and_fifteen)
    line_21_twenty_rate_tax = round_cents(line_20_twenty_rate_income * QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE)
    line_22_ordinary_tax = tax_from_schedule_y2_2025(line_5_taxable_ordinary_income, constants)
    line_23_preferential_tax = round_cents(
        line_18_fifteen_rate_tax + line_21_twenty_rate_tax + line_22_ordinary_tax
    )
    line_24_tax_on_all_taxable_income = tax_from_schedule_y2_2025(line_1_taxable_income, constants)
    regular_tax_before_credits = round_cents(min(line_23_preferential_tax, line_24_tax_on_all_taxable_income))
    return USRegularTaxAssessment2025(
        wages_usd=Decimal("0.00"),
        schedule_1_other_income_usd=Decimal("0.00"),
        adjusted_gross_income_usd=Decimal("0.00"),
        taxable_income_usd=taxable_income_usd,
        taxable_ordinary_income_usd=line_5_taxable_ordinary_income,
        ordinary_tax_component_usd=line_22_ordinary_tax,
        qualified_dividend_tax_component_usd=round_cents(line_18_fifteen_rate_tax + line_21_twenty_rate_tax),
        regular_tax_before_credits_usd=regular_tax_before_credits,
    )


def regular_tax_2025_mfs(
    taxable_income_usd: Decimal,
    qualified_dividends_usd: Decimal,
    constants: USTaxConstants2025,
    *,
    net_capital_gain_usd: Decimal = ZERO_USD,
) -> USRegularTaxAssessment2025:
    return regular_tax_2025(
        taxable_income_usd,
        qualified_dividends_usd,
        constants,
        net_capital_gain_usd=net_capital_gain_usd,
    )


def total_gross_income_for_ftc_2025(
    *,
    wages_usd: Decimal,
    ordinary_dividends_usd: Decimal,
    interest_income_usd: Decimal,
    schedule_1_other_income_usd: Decimal,
    capital_gain_distributions_usd: Decimal,
    known_positive_short_capital_gain_usd: Decimal,
    known_positive_long_capital_gain_usd: Decimal,
) -> Decimal:
    # FTC expense allocation under 26 U.S.C. § 904 and the Form 1116 instructions depends on
    # category gross income. The current model keeps the conservative documented-positive-income
    # denominator as the only supported 2025 posture. Unsupported alternatives are rejected in
    # validate_supported_us_filing_positions_2025() before the law core runs.
    #
    # § 904(b) deviation note: 26 U.S.C. § 904(b)(1) and Form 1116 line 18 conventions
    # use worldwide taxable income as the FTC fraction's denominator, with the gross-income
    # variant only as a deduction-allocation step. This module's documented-positive-income
    # denominator is conservative for the credit fraction but can drift if positive items
    # are double-counted or if the documented subset ever exceeds the
    # (taxable income + standard deduction) ceiling. The companion
    # ``validate_documented_positive_income_denominator_bound_2025`` helper enforces the
    # ceiling at ``compute_ftc_assessment_2025`` time so the deviation cannot silently
    # invert. See https://www.irs.gov/instructions/i1116 (Part III, line 18) and
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
    return round_cents(
        wages_usd
        + ordinary_dividends_usd
        + interest_income_usd
        + schedule_1_other_income_usd
        + capital_gain_distributions_usd
        + known_positive_short_capital_gain_usd
        + known_positive_long_capital_gain_usd
    )


def validate_documented_positive_income_denominator_bound_2025(
    *,
    total_gross_income_for_ftc_usd: Decimal,
    taxable_income_usd: Decimal,
    standard_deduction_usd: Decimal,
) -> None:
    # 26 U.S.C. § 904(b)(1) wants worldwide taxable income (Form 1040 line 15) as the
    # FTC fraction's denominator. The 2025 model uses the documented-positive-income
    # subset under ``conservative_positive_income_only`` (rejected to a single posture in
    # ``validate_supported_us_filing_positions_2025``). That subset is always <= worldwide
    # gross income, which itself equals taxable income + standard deduction (1040 line 12)
    # under the only supported posture (no Schedule A itemizers in this model). The
    # binding assertion here makes the invariant explicit so the deviation cannot
    # silently invert (e.g., if a future fact-extraction change ever double-counted a
    # positive item) and over-allocate deductions to a basket.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
    # https://www.irs.gov/instructions/i1116
    _require_non_negative(total_gross_income_for_ftc_usd, label="total_gross_income_for_ftc_usd")
    _require_non_negative(taxable_income_usd, label="taxable_income_usd")
    _require_non_negative(standard_deduction_usd, label="standard_deduction_usd")
    worldwide_gross_income_ceiling = round_cents(taxable_income_usd + standard_deduction_usd)
    if total_gross_income_for_ftc_usd > worldwide_gross_income_ceiling:
        # Imported lazily to avoid a module-load-time cycle with core/stages.py.
        from tax_pipeline.core.stages import LegalInvariantViolation

        raise LegalInvariantViolation(
            "US25-11-FTC-DENOMINATOR",
            "Documented-positive-income FTC denominator "
            f"{total_gross_income_for_ftc_usd} exceeds the worldwide-gross-income "
            f"ceiling {worldwide_gross_income_ceiling} = taxable_income_usd "
            f"({taxable_income_usd}) + standard_deduction_usd ({standard_deduction_usd}). "
            "26 U.S.C. § 904(b)(1) requires the FTC fraction denominator to be bounded "
            "by worldwide taxable income; under the only supported 2025 posture (no "
            "Schedule A itemizers), the documented-positive-income subset must remain "
            "<= taxable_income + standard_deduction. Investigate whether a positive "
            "income item is being double-counted before relaxing this bound."
        )


def standard_deduction_allocation_2025(
    *,
    standard_deduction_usd: Decimal,
    category_gross_income_usd: Decimal,
    total_gross_income_for_ftc_usd: Decimal,
) -> Decimal:
    # Form 1116 instructions and Publication 514 require allocating deductions between baskets.
    _require_non_negative(standard_deduction_usd, label="standard_deduction_usd")
    _require_non_negative(category_gross_income_usd, label="category_gross_income_usd")
    if total_gross_income_for_ftc_usd < ZERO_USD:
        raise ValueError("total_gross_income_for_ftc_usd must be non-negative")
    if total_gross_income_for_ftc_usd == ZERO_USD:
        if category_gross_income_usd != ZERO_USD:
            raise ValueError(
                "category_gross_income_usd must also be zero when total_gross_income_for_ftc_usd is zero"
            )
        return Decimal("0.00")
    if category_gross_income_usd == ZERO_USD:
        return Decimal("0.00")
    return standard_deduction_usd * (category_gross_income_usd / total_gross_income_for_ftc_usd)


def ftc_limitation_2025(
    *,
    regular_tax_before_credits_usd: Decimal,
    category_taxable_income_usd: Decimal,
    taxable_income_usd: Decimal,
) -> Decimal:
    # 26 U.S.C. § 904(a) limits the credit to "the same proportion of the tax against
    # which such credit is taken which the taxpayer's taxable income from sources without
    # the United States ... bears to his entire taxable income for the same taxable year."
    # Form 1116 line 21 implements this as min(line 19, line 20) — i.e. the FTC for the
    # basket cannot exceed the pre-credit U.S. tax. When the taxpayer has U.S.-source
    # losses, foreign-source taxable income can exceed worldwide taxable income, which
    # would push the unbounded fraction above 1.0 and overstate the credit. Cap at the
    # pre-credit U.S. tax to honor the statutory ceiling.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
    # https://www.irs.gov/instructions/i1116 (Part III, line 21)
    # https://www.irs.gov/publications/p514
    _require_non_negative(regular_tax_before_credits_usd, label="regular_tax_before_credits_usd")
    _require_non_negative(category_taxable_income_usd, label="category_taxable_income_usd")
    if taxable_income_usd < ZERO_USD:
        raise ValueError("taxable_income_usd must be non-negative")
    if taxable_income_usd == ZERO_USD:
        if category_taxable_income_usd != ZERO_USD:
            raise ValueError(
                "category_taxable_income_usd must also be zero when taxable_income_usd is zero"
            )
        return Decimal("0.00")
    if category_taxable_income_usd == ZERO_USD:
        return Decimal("0.00")
    return min(
        regular_tax_before_credits_usd,
        regular_tax_before_credits_usd * (category_taxable_income_usd / taxable_income_usd),
    )


def validate_form_1116_preferential_adjustment_support_2025(
    *,
    regular_tax: USRegularTaxAssessment2025,
    ftc_inputs: USFTCInputs2025,
    constants: USTaxConstants2025,
) -> None:
    # Form 1116 line 18 requires reducing worldwide taxable income when foreign qualified
    # dividends or foreign net capital gain receive preferential rates, unless the IRS
    # adjustment exception applies. The reduction worksheet is not implemented yet, so cases
    # outside the exception must stop here instead of overstating the FTC limitation.
    _require_non_negative(
        ftc_inputs.foreign_source_qualified_dividends_usd,
        label="foreign_source_qualified_dividends_usd",
    )
    _require_non_negative(
        ftc_inputs.foreign_source_net_capital_gain_usd,
        label="foreign_source_net_capital_gain_usd",
    )
    if ftc_inputs.foreign_source_net_capital_gain_usd > ftc_inputs.known_positive_long_capital_gain_usd:
        raise ValueError(
            "foreign_source_net_capital_gain_usd cannot exceed known_positive_long_capital_gain_usd"
        )

    foreign_preferential_income = round_cents(
        ftc_inputs.foreign_source_qualified_dividends_usd + ftc_inputs.foreign_source_net_capital_gain_usd
    )
    if foreign_preferential_income == ZERO_USD:
        return

    line_5_taxable_ordinary_income = regular_tax.taxable_ordinary_income_usd
    line_23_preferential_tax = round_cents(
        regular_tax.ordinary_tax_component_usd + regular_tax.qualified_dividend_tax_component_usd
    )
    line_24_tax_on_all_taxable_income = tax_from_schedule_y2_2025(
        regular_tax.taxable_income_usd,
        constants,
    )
    adjustment_required = (
        line_5_taxable_ordinary_income > ZERO_USD
        and line_23_preferential_tax < line_24_tax_on_all_taxable_income
    )
    if not adjustment_required:
        return

    # IRS Instructions for Form 1116 (2024/2025) "Adjustment exception" gates the
    # exception on FULL taxable income (Form 1040 line 15 / QDCGTW line 24), not
    # the ordinary-only portion. Using `taxable_ordinary_income_usd` here would be
    # taxpayer-favorable: a filer with significant qualified dividends could sit
    # above the bracket ceiling on full taxable income but below it on ordinary
    # income, and the exception would wrongly apply. Authority:
    # https://www.irs.gov/instructions/i1116
    qualifies_for_exception = (
        regular_tax.taxable_income_usd <= constants.tax_bracket_24_ceiling_2025_usd
        and foreign_preferential_income < FORM_1116_PREFERENTIAL_EXCEPTION_LIMIT_USD
    )
    if qualifies_for_exception:
        return

    raise NotImplementedError(
        "Form 1116 qualified-dividend/capital-gain adjustment is required, but the "
        "Worksheet for Line 18 reduction is not implemented for U.S. 2025."
    )


def current_year_general_foreign_tax_usd_2025(
    *,
    taxpayer_gross_wages_eur: Decimal,
    spouse_gross_wages_eur: Decimal,
    joint_wage_side_tax_eur: Decimal,
    eur_per_usd_yearly_average_2025: Decimal,
    use_full_joint_tax: bool = False,
) -> Decimal:
    # Publication 514 allows allocation of joint foreign tax by relative foreign-source income.
    # The current model supports only the explicit wage-share allocation posture; unsupported
    # alternatives are rejected before the law core runs.
    _require_non_negative(taxpayer_gross_wages_eur, label="taxpayer_gross_wages_eur")
    _require_non_negative(spouse_gross_wages_eur, label="spouse_gross_wages_eur")
    denominator = taxpayer_gross_wages_eur + spouse_gross_wages_eur
    _require_non_negative(joint_wage_side_tax_eur, label="joint_wage_side_tax_eur")
    _require_positive(eur_per_usd_yearly_average_2025, label="eur_per_usd_yearly_average_2025")
    if denominator == ZERO_USD:
        if joint_wage_side_tax_eur == ZERO_USD:
            return ZERO_USD
        raise ValueError("joint German wage denominator must be positive when joint wage-side tax is non-zero")
    if use_full_joint_tax:
        return round_cents(joint_wage_side_tax_eur / eur_per_usd_yearly_average_2025)
    taxpayer_share = taxpayer_gross_wages_eur / denominator
    return round_cents((joint_wage_side_tax_eur * taxpayer_share) / eur_per_usd_yearly_average_2025)


def allowed_ftc_2025(
    *,
    limitation_usd: Decimal,
    current_year_foreign_tax_usd: Decimal,
    carryover_usd: Decimal,
) -> tuple[Decimal, Decimal]:
    _require_non_negative(limitation_usd, label="limitation_usd")
    _require_non_negative(current_year_foreign_tax_usd, label="current_year_foreign_tax_usd")
    _require_non_negative(carryover_usd, label="carryover_usd")
    available = round_cents(current_year_foreign_tax_usd + carryover_usd)
    return round_cents(min(limitation_usd, available)), available


def compute_ftc_assessment_2025(
    *,
    regular_tax_before_credits_usd: Decimal,
    taxable_income_usd: Decimal,
    wages_usd: Decimal,
    capital_facts: USCapitalSourceFacts2025,
    ftc_inputs: USFTCInputs2025,
    constants: USTaxConstants2025,
    joint_us_return: bool = False,
) -> USFTCAssessment2025:
    passive_category_gross_income = round_cents(
        ftc_inputs.foreign_source_passive_dividends_usd + ftc_inputs.foreign_source_net_capital_gain_usd
    )
    total_gross_income = total_gross_income_for_ftc_2025(
        wages_usd=wages_usd,
        ordinary_dividends_usd=capital_facts.ordinary_dividends_usd,
        interest_income_usd=capital_facts.interest_income_usd,
        schedule_1_other_income_usd=round_cents(capital_facts.substitute_payments_usd + capital_facts.staking_income_usd),
        capital_gain_distributions_usd=capital_facts.capital_gain_distributions_usd,
        known_positive_short_capital_gain_usd=ftc_inputs.known_positive_short_capital_gain_usd,
        known_positive_long_capital_gain_usd=ftc_inputs.known_positive_long_capital_gain_usd,
    )
    # § 904(b)(1) ceiling: the documented-positive-income denominator must not exceed
    # worldwide gross income (taxable income + standard deduction). This is the
    # binding-assertion variant of F-US-3 — option (A) in the per-function review.
    validate_documented_positive_income_denominator_bound_2025(
        total_gross_income_for_ftc_usd=total_gross_income,
        taxable_income_usd=taxable_income_usd,
        standard_deduction_usd=constants.standard_deduction_2025_usd,
    )
    general_standard_deduction_alloc = standard_deduction_allocation_2025(
        standard_deduction_usd=constants.standard_deduction_2025_usd,
        category_gross_income_usd=wages_usd,
        total_gross_income_for_ftc_usd=total_gross_income,
    )
    passive_standard_deduction_alloc = standard_deduction_allocation_2025(
        standard_deduction_usd=constants.standard_deduction_2025_usd,
        category_gross_income_usd=passive_category_gross_income,
        total_gross_income_for_ftc_usd=total_gross_income,
    )
    general_taxable_income = max(Decimal("0.00"), wages_usd - general_standard_deduction_alloc)
    passive_taxable_income = max(Decimal("0.00"), passive_category_gross_income - passive_standard_deduction_alloc)
    general_limitation = ftc_limitation_2025(
        regular_tax_before_credits_usd=regular_tax_before_credits_usd,
        category_taxable_income_usd=general_taxable_income,
        taxable_income_usd=taxable_income_usd,
    )
    passive_limitation = ftc_limitation_2025(
        regular_tax_before_credits_usd=regular_tax_before_credits_usd,
        category_taxable_income_usd=passive_taxable_income,
        taxable_income_usd=taxable_income_usd,
    )
    current_year_general_tax = current_year_general_foreign_tax_usd_2025(
        taxpayer_gross_wages_eur=ftc_inputs.taxpayer_gross_wages_eur,
        spouse_gross_wages_eur=ftc_inputs.spouse_gross_wages_eur,
        joint_wage_side_tax_eur=ftc_inputs.joint_wage_side_tax_eur,
        eur_per_usd_yearly_average_2025=constants.eur_per_usd_yearly_average_2025,
        use_full_joint_tax=False,
    )
    allowed_general, general_available = allowed_ftc_2025(
        limitation_usd=general_limitation,
        current_year_foreign_tax_usd=current_year_general_tax,
        carryover_usd=capital_facts.general_ftc_carryover_2024_usd,
    )
    allowed_passive, passive_available = allowed_ftc_2025(
        limitation_usd=passive_limitation,
        current_year_foreign_tax_usd=capital_facts.foreign_tax_paid_usd,
        carryover_usd=capital_facts.passive_ftc_carryover_2024_usd,
    )
    total_allowed = round_cents(allowed_general + allowed_passive)
    return USFTCAssessment2025(
        total_gross_income_for_ftc_usd=round_cents(total_gross_income),
        general_standard_deduction_alloc_usd=round_cents(general_standard_deduction_alloc),
        passive_standard_deduction_alloc_usd=round_cents(passive_standard_deduction_alloc),
        general_taxable_income_for_ftc_usd=round_cents(general_taxable_income),
        passive_taxable_income_for_ftc_usd=round_cents(passive_taxable_income),
        general_ftc_limitation_usd=round_cents(general_limitation),
        passive_ftc_limitation_usd=round_cents(passive_limitation),
        current_year_general_foreign_tax_usd=current_year_general_tax,
        current_year_passive_foreign_tax_usd=round_cents(capital_facts.foreign_tax_paid_usd),
        passive_available_foreign_tax_usd=passive_available,
        general_available_foreign_tax_usd=general_available,
        allowed_general_ftc_usd=allowed_general,
        allowed_passive_ftc_usd=allowed_passive,
        total_allowed_ftc_usd=total_allowed,
        regular_tax_after_ftc_usd=round_cents(regular_tax_before_credits_usd - total_allowed),
    )


def treaty_resourcing_assessment_2025(
    *,
    ordinary_dividends_usd: Decimal,
    qualified_dividends_usd: Decimal,
    foreign_source_passive_dividends_usd: Decimal,
    foreign_source_qualified_dividends_usd: Decimal,
    taxable_income_usd: Decimal,
    standard_deduction_2025_usd: Decimal,
    regular_tax_before_credits_usd: Decimal,
    regular_tax_after_ftc_usd: Decimal,
    remaining_form_1116_line_33_cap_usd: Decimal,
    constants: USTaxConstants2025,
    treaty_inputs: USTreatyInputs2025,
) -> USTreatyResourcingAssessment2025:
    # Thin wrapper around the treaty rule graph. The legal arithmetic lives in
    # tax_pipeline/y2025/treaty_rules.py per ENGINE-RESTRUCTURE-PLAN.md (Phase 1):
    # every value in the returned dataclass is now produced by a LawRule.calculate
    # invocation through execute_rule_graph. The dataclass is kept as a typed view
    # so existing form renderers, trace writers, and golden tests continue to work
    # unchanged (option (i) in the plan).
    from tax_pipeline.y2025.treaty_rules import (
        execute_treaty_rule_graph,
        treaty_assessment_from_final_facts,
        treaty_initial_facts_2025,
        treaty_initial_fingerprints_2025,
    )

    _require_non_negative(
        remaining_form_1116_line_33_cap_usd,
        label="remaining_form_1116_line_33_cap_usd",
    )
    if treaty_inputs.use_treaty_resourcing:
        # F-FN-2: Pub. 514 worksheet line 16 average-rate denominator is taxable
        # income (Form 1040 line 15), not AGI. The wrapper now requires a positive
        # taxable_income for the average-rate path.
        _require_positive(taxable_income_usd, label="taxable_income_usd")

    initial_facts = treaty_initial_facts_2025(
        treaty_inputs=treaty_inputs,
        ordinary_dividends_usd=ordinary_dividends_usd,
        qualified_dividends_usd=qualified_dividends_usd,
        foreign_source_passive_dividends_usd=foreign_source_passive_dividends_usd,
        foreign_source_qualified_dividends_usd=foreign_source_qualified_dividends_usd,
        regular_tax_before_credits_usd=regular_tax_before_credits_usd,
        taxable_income_usd=taxable_income_usd,
        regular_tax_after_ftc_usd=regular_tax_after_ftc_usd,
        remaining_form_1116_line_33_cap_usd=remaining_form_1116_line_33_cap_usd,
    )
    execution = execute_treaty_rule_graph(
        initial_facts,
        input_fingerprints=treaty_initial_fingerprints_2025(initial_facts),
    )
    return treaty_assessment_from_final_facts(
        execution.final_facts,
        regular_tax_after_ftc_usd=regular_tax_after_ftc_usd,
    )


def niit_assessment_2025(
    *,
    adjusted_gross_income_usd: Decimal,
    capital_line_7a_usd: Decimal,
    ordinary_dividends_usd: Decimal,
    interest_income_usd: Decimal,
    substitute_payments_usd: Decimal,
    staking_income_usd: Decimal,
    include_staking_in_niit: bool,
    niit_threshold_usd: Decimal,
) -> USNIITAssessment2025:
    # 26 U.S.C. § 1411 taxes the lesser of net investment income and MAGI excess over the MFS
    # threshold. The saved posture includes staking income in NII as an explicit manual position.
    net_investment_income = ordinary_dividends_usd + interest_income_usd + substitute_payments_usd + capital_line_7a_usd
    if include_staking_in_niit:
        net_investment_income += staking_income_usd
    net_investment_income = round_cents(max(Decimal("0.00"), net_investment_income))
    modified_agi_excess = round_cents(max(Decimal("0.00"), adjusted_gross_income_usd - niit_threshold_usd))
    niit_base = round_cents(min(net_investment_income, modified_agi_excess))
    niit = round_cents(niit_base * NIIT_RATE)
    return USNIITAssessment2025(
        net_investment_income_usd=net_investment_income,
        modified_agi_excess_usd=modified_agi_excess,
        niit_base_usd=niit_base,
        niit_usd=niit,
    )


@dataclass(frozen=True)
class USFEIEAssessment2025:
    """26 U.S.C. § 911 FEIE / housing-exclusion / housing-deduction
    breakdown produced by ``feie_assessment_2025``.

    All values are in cent-rounded USD. ``elected`` mirrors the input
    flag so downstream consumers do not have to look at the inputs.
    ``disallowed_ftc_usd`` is the foreign tax that § 911(d)(6) denies as
    a credit because it is allocable to the excluded amount.
    ``niit_magi_addback_usd`` is the § 1411(d)(1)(A) MAGI add-back of
    the excluded amount for NIIT purposes.
    """

    elected: bool
    excluded_amount_usd: Decimal
    housing_exclusion_usd: Decimal
    housing_deduction_usd: Decimal
    deduction_total_usd: Decimal
    disallowed_ftc_usd: Decimal
    niit_magi_addback_usd: Decimal


def feie_assessment_2025(
    *,
    feie_inputs: USFEIEInputs2025,
) -> USFEIEAssessment2025:
    """Compute the § 911 / § 911(c) FEIE + housing exclusion / deduction.

    Authority:
      - 26 U.S.C. § 911(b)(2)(D) — annual exclusion ($130,000 for 2025).
      - 26 U.S.C. § 911(c)(1)/(2) — housing exclusion = qualifying
        housing expenses minus § 911(c)(1)(B) base (16 % of FEIE),
        capped by the location-adjusted ceiling (default 30 % of FEIE
        per IRS Notice 2024-77).
      - 26 U.S.C. § 911(c)(4) — self-employed taxpayers route the same
        amount to the housing deduction (limited to remaining foreign
        earned income after exclusions).
      - 26 U.S.C. § 911(d)(6) — denies FTC on foreign tax allocable to
        excluded income.
      - 26 U.S.C. § 1411(d)(1)(A) — MAGI add-back of § 911 excluded
        amount for NIIT purposes.

    URLs: see ``USC_911_URL`` and ``IRS_P54_URL`` /
    ``IRS_FORM_2555_URL`` / ``IRS_NOTICE_2024_77_URL``.
    """
    if not feie_inputs.elected:
        return USFEIEAssessment2025(
            elected=False,
            excluded_amount_usd=ZERO_USD,
            housing_exclusion_usd=ZERO_USD,
            housing_deduction_usd=ZERO_USD,
            deduction_total_usd=ZERO_USD,
            disallowed_ftc_usd=ZERO_USD,
            niit_magi_addback_usd=ZERO_USD,
        )
    qualifying = (feie_inputs.qualifying_test or "").strip().lower()
    if qualifying not in ("bona_fide_residence", "physical_presence"):
        # § 911(d)(1) requires one of the two qualifying tests; an empty
        # or unrecognized value is fail-closed material.
        raise ValueError(
            "FEIE election requires qualifying_test in "
            "{'bona_fide_residence', 'physical_presence'} per § 911(d)(1)."
        )
    _require_non_negative(
        feie_inputs.foreign_earned_income_usd,
        label="foreign_earned_income_usd",
    )
    _require_non_negative(
        feie_inputs.housing_expenses_usd,
        label="housing_expenses_usd",
    )
    _require_non_negative(
        feie_inputs.foreign_tax_paid_on_excluded_income_usd,
        label="foreign_tax_paid_on_excluded_income_usd",
    )
    if feie_inputs.location_adjusted_housing_ceiling_usd is not None:
        _require_non_negative(
            feie_inputs.location_adjusted_housing_ceiling_usd,
            label="location_adjusted_housing_ceiling_usd",
        )
    # § 911(b)(2)(D): excluded amount cannot exceed gross foreign earned
    # income or the indexed annual ceiling.
    excluded_amount = round_cents(
        min(feie_inputs.foreign_earned_income_usd, SECTION_911_FEIE_2025_USD)
    )
    # § 911(c)(1)(B) base housing amount = 16 % of FEIE ceiling.
    housing_base = round_cents(SECTION_911_FEIE_2025_USD * SECTION_911_HOUSING_BASE_RATE)
    # § 911(c)(2)(A) ceiling = 30 % of FEIE OR location-adjusted amount
    # from IRS Notice 2024-77 (still rounded to cents).
    if feie_inputs.location_adjusted_housing_ceiling_usd is not None:
        housing_ceiling = round_cents(
            feie_inputs.location_adjusted_housing_ceiling_usd
        )
    else:
        housing_ceiling = round_cents(
            SECTION_911_FEIE_2025_USD * SECTION_911_HOUSING_CEILING_RATE
        )
    # Housing amount = min(qualifying_expenses, ceiling) - base, floored
    # at zero. § 911(c)(2)(A) describes the cap; § 911(c)(1)(B) the base.
    capped_expenses = min(feie_inputs.housing_expenses_usd, housing_ceiling)
    housing_amount = round_cents(max(ZERO_USD, capped_expenses - housing_base))
    if feie_inputs.self_employed:
        # § 911(c)(4): self-employed taxpayer's housing amount routes to
        # the housing deduction, limited to remaining foreign earned
        # income (FEI − § 911 exclusion).
        remaining_fei = max(
            ZERO_USD, feie_inputs.foreign_earned_income_usd - excluded_amount
        )
        housing_deduction = round_cents(min(housing_amount, remaining_fei))
        housing_exclusion = ZERO_USD
    else:
        housing_exclusion = housing_amount
        housing_deduction = ZERO_USD
    deduction_total = round_cents(
        excluded_amount + housing_exclusion + housing_deduction
    )
    # § 911(d)(6): foreign tax paid on the excluded portion of foreign
    # earned income is denied as a credit. The supplied input names
    # exactly that already-allocated amount; do not pro-rate again here.
    disallowed_ftc = round_cents(
        feie_inputs.foreign_tax_paid_on_excluded_income_usd
    )
    # § 1411(d)(1)(A): excluded amount adds back to MAGI for NIIT.
    niit_magi_addback = round_cents(excluded_amount + housing_exclusion)
    return USFEIEAssessment2025(
        elected=True,
        excluded_amount_usd=excluded_amount,
        housing_exclusion_usd=housing_exclusion,
        housing_deduction_usd=housing_deduction,
        deduction_total_usd=deduction_total,
        disallowed_ftc_usd=disallowed_ftc,
        niit_magi_addback_usd=niit_magi_addback,
    )


# ---------------------------------------------------------------------------
# FATCA Form 8938 + FinCEN Form 114 (FBAR) determination — 2025
# ---------------------------------------------------------------------------
# Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03). The two regimes are
# determinations only — they do not change tax owed. The engine computes
# REQUIRED / NOT REQUIRED and surfaces both as status sheets so the user
# can confirm whether to attach Form 8938 to Form 1040 and/or file FBAR
# with FinCEN. Authority: 26 U.S.C. § 6038D / Reg. § 1.6038D-2 / 31
# U.S.C. § 5314 / 31 CFR § 1010.350.


@dataclass(frozen=True)
class USForeignFinancialAccount2025:
    """A single foreign financial account loaded from
    ``years/<workspace>/normalized/facts/foreign-financial-accounts.csv``.

    The CSV is the authoritative input: balances are user-supplied
    (typically transcribed from year-end bank/broker statements). The
    engine does NOT derive these from raw documents in this Phase D
    (Group D, FORM-MAPPING-FOLLOWUP, 2026-05-03); a derivation that
    auto-populates the CSV from raw broker / German-bank / crypto
    statements is a follow-on improvement.

    ``is_specified_foreign_financial_asset`` (SFFA) gates Form 8938
    scope (§ 6038D / Reg. § 1.6038D-3). FBAR scope (31 CFR § 1010.350)
    is broader — every foreign financial account counts, even if not a
    SFFA. Both balances are USD-translated already (the CSV requires
    a USD column alongside any source-currency column).
    """

    account_id: str
    country: str
    institution: str
    account_type: str  # bank | brokerage | pension | insurance | other
    currency: str
    usd_max_balance_during_year: Decimal
    usd_eoy_balance: Decimal
    is_specified_foreign_financial_asset: bool


@dataclass(frozen=True)
class USFATCAFBARInputs2025:
    """Inputs to the US25-FATCA-FBAR-DETERMINATION stage.

    ``filing_status_label`` mirrors ``USReturnProfile2025.filing_status_label``
    and selects which Form 8938 threshold pair applies. ``residency_basis``
    selects the abroad vs. domestic threshold tier:

      - ``"abroad_section_911_d_1_a"`` — bona-fide resident of a foreign
        country under § 911(d)(1)(A) for the year (Reg. § 1.6038D-2(b)(1)
        first prong).
      - ``"abroad_330_day_physical_presence"`` — present in foreign
        countries 330+ days of any 12-month period ending in the tax year
        (Reg. § 1.6038D-2(b)(1) second prong).
      - ``"domestic"`` — neither prong satisfied; standard thresholds.

    ``accounts`` is the per-account fact list. ``data_complete`` is the
    explicit "this CSV exhaustively enumerates the user's foreign
    accounts" flag. When False the rule fails closed with
    ``not_applicable`` carrying a citation, per CLAUDE.md fail-closed
    posture.
    """

    filing_status_label: str
    residency_basis: str
    accounts: tuple[USForeignFinancialAccount2025, ...]
    data_complete: bool


@dataclass(frozen=True)
class USFATCAFBARAssessment2025:
    """Output of ``fatca_fbar_assessment_2025``."""

    status: str  # "determined" | "not_applicable"
    reason: str
    form_8938_threshold_eoy_usd: Decimal
    form_8938_threshold_anytime_usd: Decimal
    foreign_specified_assets_max_usd: Decimal
    foreign_specified_assets_eoy_usd: Decimal
    form_8938_required: bool
    fbar_aggregate_max_balance_usd: Decimal
    fincen_114_required: bool


def _fatca_8938_thresholds_2025_usd(
    *,
    filing_status_label: str,
    residency_basis: str,
) -> tuple[Decimal, Decimal]:
    """Return ``(eoy_threshold_usd, anytime_threshold_usd)`` per Reg.
    § 1.6038D-2(b). Fails closed on any unrecognized filing-status /
    residency combination so a future posture cannot silently default
    to a domestic threshold for an abroad filer.
    """
    status = filing_status_label.strip().lower()
    basis = residency_basis.strip().lower()
    abroad = basis in {"abroad_section_911_d_1_a", "abroad_330_day_physical_presence"}
    if status == "married filing jointly":
        if abroad:
            return (
                FATCA_8938_THRESHOLD_ABROAD_MFJ_EOY_USD,
                FATCA_8938_THRESHOLD_ABROAD_MFJ_ANYTIME_USD,
            )
        return (
            FATCA_8938_THRESHOLD_DOMESTIC_MFJ_EOY_USD,
            FATCA_8938_THRESHOLD_DOMESTIC_MFJ_ANYTIME_USD,
        )
    if status in {"single", "married filing separately", "head of household"}:
        if abroad:
            return (
                FATCA_8938_THRESHOLD_ABROAD_SINGLE_EOY_USD,
                FATCA_8938_THRESHOLD_ABROAD_SINGLE_ANYTIME_USD,
            )
        return (
            FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_EOY_USD,
            FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_ANYTIME_USD,
        )
    raise ValueError(
        f"Unsupported filing-status / residency-basis pair for Form 8938: "
        f"filing_status_label={filing_status_label!r}, "
        f"residency_basis={residency_basis!r}. Reg. § 1.6038D-2(b) "
        f"thresholds are filing-status- and residency-dependent; the "
        f"engine fails closed rather than guessing a tier."
    )


def fatca_fbar_assessment_2025(
    *,
    inputs: USFATCAFBARInputs2025,
) -> USFATCAFBARAssessment2025:
    """Compute the Form 8938 (§ 6038D) and FBAR (31 CFR § 1010.350)
    filing determinations.

    This is a determination-only function; the outputs do not change
    tax owed. CLAUDE.md fail-closed posture applies: if
    ``inputs.data_complete=False`` (or filing_status_label is missing)
    the rule must surface ``status="not_applicable"`` with a citation
    rather than silently treating "no data" as "below threshold". The
    renderer reads ``status`` and emits the manual-determination text
    in that case.

    Authority:
      - 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
      - 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
      - IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
      - 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
      - 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
      - FinCEN BSA E-Filing — https://bsaefiling.fincen.treas.gov/
    """
    # Fail-closed shortcut: an empty filing_status_label means a
    # caller / loader-default that has not yet wired a real posture
    # (default ``USAssessmentInputs2025`` produces this when an
    # ad-hoc test constructs an inputs bundle without the FATCA hook).
    # Surface the manual-determination status instead of raising on the
    # threshold lookup.
    if not (inputs.filing_status_label or "").strip():
        return USFATCAFBARAssessment2025(
            status="not_applicable",
            reason=(
                "Filing status not supplied to FATCA / FBAR determination. "
                "26 U.S.C. § 6038D thresholds are filing-status- and "
                "residency-dependent; supply filing_status_label and a "
                "populated foreign-financial-accounts.csv to enable the "
                "determination."
            ),
            form_8938_threshold_eoy_usd=ZERO_USD,
            form_8938_threshold_anytime_usd=ZERO_USD,
            foreign_specified_assets_max_usd=ZERO_USD,
            foreign_specified_assets_eoy_usd=ZERO_USD,
            form_8938_required=False,
            fbar_aggregate_max_balance_usd=ZERO_USD,
            fincen_114_required=False,
        )
    eoy_threshold, anytime_threshold = _fatca_8938_thresholds_2025_usd(
        filing_status_label=inputs.filing_status_label,
        residency_basis=inputs.residency_basis,
    )
    if not inputs.data_complete:
        # Fail-closed: foreign-account fact source is not yet populated
        # for this workspace. The engine surfaces a "manual determination
        # required" status; the renderer emits the citation-bearing
        # explanatory text. Decimal aggregates are zero by construction
        # because no balance data was supplied; the booleans are False
        # because we cannot affirmatively determine that thresholds are
        # exceeded without complete data — but the status sheet flags
        # this explicitly so a $0 here is NOT mistaken for "below
        # threshold". 26 U.S.C. § 6038D / 31 CFR § 1010.350.
        #
        # Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): when the loader
        # populated ``inputs.accounts`` from the auto-derived stub CSV,
        # the rule enriches the ``reason`` text with a per-account
        # enumeration so the renderer / user sees "fill in balances for
        # these N discovered accounts" rather than "populate this CSV
        # from scratch". The list is appended deterministically (sorted
        # by account_id) and bounded so a workspace with hundreds of
        # accounts does not produce an unboundedly long reason string.
        if inputs.accounts:
            sorted_accounts = sorted(inputs.accounts, key=lambda a: a.account_id)
            preview_count = min(10, len(sorted_accounts))
            account_summary = "; ".join(
                f"{a.account_id} ({a.country}, {a.institution}, {a.account_type})"
                for a in sorted_accounts[:preview_count]
            )
            tail = (
                f" (and {len(sorted_accounts) - preview_count} more)"
                if len(sorted_accounts) > preview_count
                else ""
            )
            reason = (
                f"Foreign-financial-account balances are unverified for "
                f"this workspace. {len(sorted_accounts)} foreign account(s) "
                f"have been auto-discovered from extracted facts: "
                f"{account_summary}{tail}. 26 U.S.C. § 6038D / 31 CFR "
                f"§ 1010.350 thresholds cannot be evaluated without "
                f"per-account end-of-year and max-during-year balances. "
                f"Edit years/<workspace>/normalized/facts/"
                f"foreign-financial-accounts.csv to fill in usd_eoy_balance "
                f"and usd_max_balance_during_year for each account, then "
                f"add the __data_complete__ sentinel row."
            )
        else:
            reason = (
                "Foreign-financial-account fact source not yet populated "
                "for this workspace. 26 U.S.C. § 6038D / 31 CFR § 1010.350 "
                "thresholds cannot be evaluated without per-account "
                "balances. Populate years/<workspace>/normalized/facts/"
                "foreign-financial-accounts.csv and set data_complete=true."
            )
        return USFATCAFBARAssessment2025(
            status="not_applicable",
            reason=reason,
            form_8938_threshold_eoy_usd=eoy_threshold,
            form_8938_threshold_anytime_usd=anytime_threshold,
            foreign_specified_assets_max_usd=ZERO_USD,
            foreign_specified_assets_eoy_usd=ZERO_USD,
            form_8938_required=False,
            fbar_aggregate_max_balance_usd=ZERO_USD,
            fincen_114_required=False,
        )
    # § 6038D scope: only "specified foreign financial assets" count
    # toward the Form 8938 thresholds.
    sffa_max = ZERO_USD
    sffa_eoy = ZERO_USD
    fbar_aggregate_max = ZERO_USD
    for account in inputs.accounts:
        _require_non_negative(
            account.usd_max_balance_during_year,
            label=f"account[{account.account_id}].usd_max_balance_during_year",
        )
        _require_non_negative(
            account.usd_eoy_balance,
            label=f"account[{account.account_id}].usd_eoy_balance",
        )
        # FBAR scope (31 CFR § 1010.350) is broader than § 6038D — every
        # foreign financial account counts toward the $10,000 aggregate.
        fbar_aggregate_max += account.usd_max_balance_during_year
        if account.is_specified_foreign_financial_asset:
            sffa_max += account.usd_max_balance_during_year
            sffa_eoy += account.usd_eoy_balance
    sffa_max = round_cents(sffa_max)
    sffa_eoy = round_cents(sffa_eoy)
    fbar_aggregate_max = round_cents(fbar_aggregate_max)
    # Reg. § 1.6038D-2(a): Form 8938 attaches if EITHER the EOY value
    # exceeds the EOY threshold OR the max-anytime value exceeds the
    # anytime threshold.
    form_8938_required = (sffa_eoy > eoy_threshold) or (sffa_max > anytime_threshold)
    # 31 CFR § 1010.350(a): FBAR attaches if aggregate max balance during
    # year exceeds $10,000.
    fincen_114_required = fbar_aggregate_max > FBAR_AGGREGATE_THRESHOLD_USD
    return USFATCAFBARAssessment2025(
        status="determined",
        reason="",
        form_8938_threshold_eoy_usd=eoy_threshold,
        form_8938_threshold_anytime_usd=anytime_threshold,
        foreign_specified_assets_max_usd=sffa_max,
        foreign_specified_assets_eoy_usd=sffa_eoy,
        form_8938_required=form_8938_required,
        fbar_aggregate_max_balance_usd=fbar_aggregate_max,
        fincen_114_required=fincen_114_required,
    )


@dataclass(frozen=True)
class USSelfEmploymentTaxAssessment2025:
    """26 U.S.C. § 1401 Self-Employment tax breakdown."""

    net_se_earnings_usd: Decimal
    se_taxable_earnings_usd: Decimal  # 92.35 % of net SE earnings
    oasdi_taxable_earnings_usd: Decimal  # capped at SS wage base
    oasdi_tax_usd: Decimal
    medicare_tax_usd: Decimal
    se_tax_usd: Decimal


def se_tax_assessment_2025(
    *,
    se_inputs: USSelfEmploymentInputs2025,
) -> USSelfEmploymentTaxAssessment2025:
    """Compute § 1401 OASDI + Medicare SE tax.

    Authority:
      - 26 U.S.C. § 1401(a) — 12.4 % OASDI on net SE earnings up to the
        SSA wage base.
      - 26 U.S.C. § 1401(b)(1) — 2.9 % Medicare on all net SE earnings.
      - 26 U.S.C. § 1402(a)(12) — net SE earnings × 92.35 %.
      - § 1401(b)(2) Additional Medicare 0.9 % is computed in the
        separate ``additional_medicare_assessment_2025`` so it can be
        combined with the wage-side computation per Form 8959.

    URLs: see ``USC_1401_URL`` / ``USC_1402_URL`` /
    ``IRS_SCHEDULE_SE_URL``.
    """
    _require_non_negative(
        se_inputs.net_se_earnings_usd, label="net_se_earnings_usd"
    )
    if se_inputs.totalization_certificate_present:
        # U.S.-Germany Totalization Agreement (1979) keeps SE earnings
        # OUT of U.S. § 1401 if a German Certificate of Coverage applies.
        # The certificate-driven path is a future workstream — fail closed.
        raise NotImplementedError(
            "U.S.-Germany Totalization Agreement Certificate of Coverage "
            "exempts SE earnings from § 1401. Certificate handling is not "
            "implemented for 2025; remove the certificate flag or "
            "implement the SSA-coverage path before computing SE tax. "
            "Authority: SSA U.S.-Germany Totalization Agreement "
            f"({SSA_TOTALIZATION_DE_URL})."
        )
    if se_inputs.net_se_earnings_usd <= ZERO_USD:
        return USSelfEmploymentTaxAssessment2025(
            net_se_earnings_usd=ZERO_USD,
            se_taxable_earnings_usd=ZERO_USD,
            oasdi_taxable_earnings_usd=ZERO_USD,
            oasdi_tax_usd=ZERO_USD,
            medicare_tax_usd=ZERO_USD,
            se_tax_usd=ZERO_USD,
        )
    se_taxable = round_cents(
        se_inputs.net_se_earnings_usd * SECA_NET_EARNINGS_FACTOR
    )
    oasdi_base = round_cents(min(se_taxable, SS_WAGE_BASE_2025_USD))
    oasdi_tax = round_cents(oasdi_base * OASDI_RATE)
    medicare_tax = round_cents(se_taxable * MEDICARE_RATE)
    se_tax = round_cents(oasdi_tax + medicare_tax)
    return USSelfEmploymentTaxAssessment2025(
        net_se_earnings_usd=round_cents(se_inputs.net_se_earnings_usd),
        se_taxable_earnings_usd=se_taxable,
        oasdi_taxable_earnings_usd=oasdi_base,
        oasdi_tax_usd=oasdi_tax,
        medicare_tax_usd=medicare_tax,
        se_tax_usd=se_tax,
    )


@dataclass(frozen=True)
class USAdditionalMedicareAssessment2025:
    """26 U.S.C. § 3101(b)(2) + § 1401(b)(2) Additional Medicare Tax."""

    threshold_usd: Decimal
    medicare_wages_usd: Decimal
    se_taxable_earnings_usd: Decimal
    combined_base_usd: Decimal
    excess_over_threshold_usd: Decimal
    additional_medicare_tax_usd: Decimal


def _additional_medicare_threshold_2025(filing_status_label: str) -> Decimal:
    text = (filing_status_label or "").strip().lower()
    if text == "single":
        return ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD
    if text == "married filing jointly":
        return ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD
    if text == "married filing separately":
        return ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD
    raise NotImplementedError(
        "Additional Medicare threshold not implemented for U.S. filing "
        f"status {filing_status_label!r}; expected 'Single', 'Married "
        "filing jointly', or 'Married filing separately'."
    )


def additional_medicare_assessment_2025(
    *,
    filing_status_label: str,
    medicare_taxable_wages_usd: Decimal,
    se_taxable_earnings_usd: Decimal,
) -> USAdditionalMedicareAssessment2025:
    """Compute § 3101(b)(2) + § 1401(b)(2) Additional Medicare tax.

    Authority:
      - 26 U.S.C. § 3101(b)(2) — 0.9 % additional Medicare tax on wages
        above filing-status threshold.
      - 26 U.S.C. § 1401(b)(2) — same 0.9 % on SE earnings, sharing the
        same threshold (single threshold across wages + SE per
        Form 8959 Part III).
      - Form 8959 instructions — combined wage/SE base.

    URLs: see ``USC_3101_URL`` and ``IRS_FORM_8959_URL``.
    """
    _require_non_negative(
        medicare_taxable_wages_usd, label="medicare_taxable_wages_usd"
    )
    _require_non_negative(
        se_taxable_earnings_usd, label="se_taxable_earnings_usd"
    )
    threshold = _additional_medicare_threshold_2025(filing_status_label)
    combined = round_cents(medicare_taxable_wages_usd + se_taxable_earnings_usd)
    excess = round_cents(max(ZERO_USD, combined - threshold))
    addtl_tax = round_cents(excess * ADDITIONAL_MEDICARE_RATE)
    return USAdditionalMedicareAssessment2025(
        threshold_usd=threshold,
        medicare_wages_usd=round_cents(medicare_taxable_wages_usd),
        se_taxable_earnings_usd=round_cents(se_taxable_earnings_usd),
        combined_base_usd=combined,
        excess_over_threshold_usd=excess,
        additional_medicare_tax_usd=addtl_tax,
    )


# ---------------------------------------------------------------------------
# Schedule B render-precondition (Workstream 5)
# ---------------------------------------------------------------------------
# IRS Form 1040 Instructions / Schedule B Instructions: Schedule B is
# required when ANY of the following holds:
#   - Taxable interest exceeds $1,500
#   - Ordinary dividends exceed $1,500
#   - The taxpayer has a foreign account (Schedule B Part III is
#     ALWAYS required when a foreign account exists, regardless of the
#     $1,500 thresholds)
#   - Other less-common triggers (accrued bond interest, S-corp, etc.)
# https://www.irs.gov/instructions/i1040gi
# https://www.irs.gov/forms-pubs/about-schedule-b-form-1040
SCHEDULE_B_THRESHOLD_USD = Decimal("1500.00")
IRS_SCHEDULE_B_URL = "https://www.irs.gov/forms-pubs/about-schedule-b-form-1040"


@dataclass(frozen=True)
class USChildTaxCreditAssessment2025:
    """View of the executed US25-CTC-AND-ODC stage.

    All amounts are cents-rounded USD. The two components — the
    nonrefundable portion (Form 1040 line 19) and the refundable
    Additional Child Tax Credit (Form 1040 line 28) — are tracked
    separately because § 24(d) routes them to different form lines
    and the refundable portion is capped per § 24(d)(1)(B) at the
    earned-income phase-in amount.

    Authority: 26 U.S.C. § 24 (CTC + ACTC + ODC).
    https://www.law.cornell.edu/uscode/text/26/24
    """

    children_count_qualifying_for_ctc: int
    children_count_qualifying_for_odc: int
    # Schedule 8812 (2025) Line 4 / Line 6 — qualifying-children counts.
    # § 24(c)(1) qualifying child / § 24(h)(7) SSN requirement (CTC) and
    # § 24(h)(4) qualifying relatives / non-SSN children (ODC).
    qualifying_ctc_count: int
    qualifying_odc_count: int
    gross_ctc_usd: Decimal
    gross_odc_usd: Decimal
    combined_pre_phaseout_usd: Decimal
    phaseout_threshold_usd: Decimal
    # Schedule 8812 Line 10 — Modified AGI (§ 24(b)(2)). AGI plus the
    # § 911 / § 911(c) excluded foreign earned income (the same MAGI add-
    # back § 1411(d)(1)(A) applies to the NIIT base) plus § 933 / Form
    # 2555 excluded amounts. Surfacing it as a declared output makes the
    # MAGI source auditable line by line.
    modified_agi_usd: Decimal
    magi_excess_usd: Decimal
    phaseout_reduction_usd: Decimal
    combined_post_phaseout_usd: Decimal
    # Schedule 8812 Line 13 — the regular-tax-after-FTC ordering cap.
    # § 24(b)(3) ordering: nonrefundable credits cannot reduce tax below
    # zero; the Credit Limit Worksheet A on the Schedule 8812 (2025)
    # instructions surfaces this cap explicitly.
    regular_tax_after_ftc_usd: Decimal
    nonrefundable_portion_usd: Decimal
    # Schedule 8812 Line 16a — the post-phaseout CTC remaining after the
    # nonrefundable allocation absorbed regular tax.
    remaining_ctc_for_refundable_usd: Decimal
    refundable_actc_cap_usd: Decimal
    # Schedule 8812 Line 18a — earned income input to the § 24(d)(1)(B)
    # phase-in. Wages (§ 32(c)(2)(A)) plus net SE earnings
    # (§ 32(c)(2)(B)), reduced by the § 911 excluded portion under
    # § 24(d)(1)(B)(i).
    earned_income_usd: Decimal
    # Schedule 8812 Line 19 — the statutory $2,500 earned-income floor
    # under § 24(d)(1)(B). Surfaced as a declared output (constant value)
    # so the audit graph records where the floor was sourced.
    earned_income_floor_usd: Decimal
    # Schedule 8812 Line 20 — max(0, earned_income − $2,500).
    earned_income_excess_usd: Decimal
    refundable_actc_earned_income_phase_in_usd: Decimal
    # Post-phaseout CTC slice = combined_post × gross_ctc / combined_pre.
    # Used to compute Schedule 8812 Line 16a remaining-CTC ceiling.
    post_phaseout_ctc_share_usd: Decimal
    refundable_actc_usd: Decimal
    total_credit_usd: Decimal


def _ctc_phaseout_threshold_2025(*, filing_status_label: str) -> Decimal:
    # § 24(b)(2): MFJ uses the $400,000 threshold; all other filing
    # statuses (Single, HoH, MFS, Surviving spouse) use the $200,000
    # threshold under the post-TCJA / OBBBA-extended numerics.
    label = filing_status_label.strip().lower()
    if label == "married filing jointly":
        return CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD
    return CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD


def ctc_and_odc_assessment_2025(
    *,
    children_count_qualifying_for_ctc: int,
    children_count_qualifying_for_odc: int,
    earned_income_usd: Decimal,
    modified_agi_usd: Decimal,
    regular_tax_after_ftc_usd: Decimal,
    filing_status_label: str,
) -> USChildTaxCreditAssessment2025:
    """26 U.S.C. § 24 Child Tax Credit + ODC assessment for 2025.

    Authority:
      - § 24(a) (as substituted by § 24(h)(2) post-OBBBA for 2025):
        $2,200 CTC per qualifying child (§ 152(c)).
      - § 24(b)(2): phase-out begins at $200k single / $400k MFJ;
        $50 reduction per $1,000 of MAGI excess (round excess up to
        the next $1,000 per § 24(b)(3)).
      - § 24(d)(1)(A) refundable ACTC cap: $1,700 per qualifying
        child for 2025 (Rev. Proc. 2024-40 § 3.05). § 24(d)(1)(B)
        formula: 15 % × (earned income − $2,500).
      - § 24(h)(4): $500 ODC per qualifying child 17+ or qualifying
        relative with TIN (NON-refundable).
      - § 24(h)(7): CTC requires a valid SSN issued before the due
        date of the return (the loader handles classification before
        the assessment runs).

    https://www.law.cornell.edu/uscode/text/26/24
    https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
    https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
    """
    if children_count_qualifying_for_ctc < 0:
        raise ValueError("children_count_qualifying_for_ctc must be non-negative")
    if children_count_qualifying_for_odc < 0:
        raise ValueError("children_count_qualifying_for_odc must be non-negative")
    _require_non_negative(earned_income_usd, label="earned_income_usd")
    _require_non_negative(modified_agi_usd, label="modified_agi_usd")
    _require_non_negative(regular_tax_after_ftc_usd, label="regular_tax_after_ftc_usd")

    gross_ctc = round_cents(
        Decimal(children_count_qualifying_for_ctc) * CTC_PER_CHILD_2025_USD
    )
    gross_odc = round_cents(
        Decimal(children_count_qualifying_for_odc) * ODC_PER_DEPENDENT_2025_USD
    )
    combined_pre = round_cents(gross_ctc + gross_odc)

    threshold = _ctc_phaseout_threshold_2025(filing_status_label=filing_status_label)
    magi_excess = max(ZERO_USD, modified_agi_usd - threshold)
    # § 24(b)(3) round excess up to next $1,000 before applying the
    # 5 %-per-$1,000 rate (= $50 per $1,000). Use ROUND_FLOOR to compute
    # ceil via -((-x) // 1000) * 1000.
    one_thousand = Decimal("1000")
    excess_quotient = magi_excess / one_thousand
    # Ceil to next integer:
    excess_thousands = (-((-excess_quotient).to_integral_value(rounding=ROUND_FLOOR)))
    rounded_excess_for_reduction = round_cents(excess_thousands * one_thousand)
    phaseout_reduction = round_cents(rounded_excess_for_reduction * CTC_PHASEOUT_RATE)
    if phaseout_reduction > combined_pre:
        phaseout_reduction = combined_pre
    combined_post = round_cents(combined_pre - phaseout_reduction)

    # Nonrefundable portion is the part of the combined post-phaseout
    # credit that offsets regular tax after FTC. It is capped at the
    # regular-tax-after-FTC value (§ 24(b)(3) ordering: nonrefundable
    # credits cannot reduce tax below zero).
    nonrefundable_portion = round_cents(min(combined_post, regular_tax_after_ftc_usd))

    # Refundable ACTC under § 24(d)(1):
    #   refundable = min(remaining_ctc, $1,700/child, 15% × max(0, earned_income − $2,500))
    # ODC is NOT refundable, so allocate the nonrefundable_portion to
    # CTC first (§ 24 ordering): the remaining-CTC ceiling is the part
    # of the post-phaseout CTC that did not absorb regular tax. When
    # combined_post equals gross CTC + ODC, allocate nonrefundable to
    # ODC first only up to gross_odc — anything above absorbs CTC.
    # Conservative allocation: assume nonrefundable absorbed CTC first,
    # so refundable ceiling = max(0, post-phaseout CTC − nonrefundable).
    # When phase-out applies it reduces CTC and ODC pro rata; collapse
    # to combined_post then split: post-phaseout CTC share =
    # combined_post × gross_ctc / combined_pre (cents-rounded).
    if combined_pre > ZERO_USD:
        post_phaseout_ctc = round_cents(combined_post * gross_ctc / combined_pre)
    else:
        post_phaseout_ctc = ZERO_USD
    remaining_ctc_for_refundable = max(ZERO_USD, post_phaseout_ctc - nonrefundable_portion)
    refundable_per_child_cap = round_cents(
        Decimal(children_count_qualifying_for_ctc)
        * CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD
    )
    earned_income_excess = max(
        ZERO_USD, earned_income_usd - CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD
    )
    earned_income_phase_in = round_cents(
        earned_income_excess * CTC_REFUNDABLE_PHASE_IN_RATE
    )
    refundable_actc = round_cents(
        min(
            remaining_ctc_for_refundable,
            refundable_per_child_cap,
            earned_income_phase_in,
        )
    )
    if refundable_actc < ZERO_USD:
        refundable_actc = ZERO_USD
    total_credit = round_cents(nonrefundable_portion + refundable_actc)

    return USChildTaxCreditAssessment2025(
        children_count_qualifying_for_ctc=children_count_qualifying_for_ctc,
        children_count_qualifying_for_odc=children_count_qualifying_for_odc,
        # Schedule 8812 (2025) Line 4 / Line 6 — counts. The qualifying-
        # children counts surface as their own legal outputs (and Schedule
        # 8812 line refs) so a downstream auditor can read the
        # § 24(c)(1) / § 24(h)(4) classification straight off the audit
        # graph rather than re-executing the loader's child classifier.
        qualifying_ctc_count=children_count_qualifying_for_ctc,
        qualifying_odc_count=children_count_qualifying_for_odc,
        gross_ctc_usd=gross_ctc,
        gross_odc_usd=gross_odc,
        combined_pre_phaseout_usd=combined_pre,
        phaseout_threshold_usd=threshold,
        # Schedule 8812 Line 10 — § 24(b)(2) Modified AGI. The caller
        # already folded in § 911 / § 933 add-backs upstream (the rule
        # body builds magi from agi + niit_magi_addback_usd). Echoing it
        # here makes Line 10 a declared rule output (see invariant I2).
        modified_agi_usd=round_cents(modified_agi_usd),
        magi_excess_usd=round_cents(magi_excess),
        phaseout_reduction_usd=phaseout_reduction,
        combined_post_phaseout_usd=combined_post,
        # Schedule 8812 Line 13 — regular tax after FTC. § 24(b)(3) caps
        # the nonrefundable portion at this value (nonrefundable credits
        # cannot reduce tax below zero). Echoed as a declared output so
        # the Credit Limit Worksheet A entry traces to a real fingerprint.
        regular_tax_after_ftc_usd=round_cents(regular_tax_after_ftc_usd),
        nonrefundable_portion_usd=nonrefundable_portion,
        # Schedule 8812 Line 16a — post-phaseout CTC slice that did not
        # absorb regular tax (the refundable-ACTC ceiling under § 24(d)).
        remaining_ctc_for_refundable_usd=remaining_ctc_for_refundable,
        refundable_actc_cap_usd=refundable_per_child_cap,
        # Schedule 8812 Line 18a — earned income input to § 24(d)(1)(B).
        earned_income_usd=round_cents(earned_income_usd),
        # Schedule 8812 Line 19 — § 24(d)(1)(B) statutory $2,500 floor.
        # Sourced from CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD (invariant
        # I1: legal constants live in the law module).
        earned_income_floor_usd=round_cents(CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD),
        # Schedule 8812 Line 20 — max(0, earned_income − $2,500).
        earned_income_excess_usd=round_cents(earned_income_excess),
        refundable_actc_earned_income_phase_in_usd=earned_income_phase_in,
        # Post-phaseout CTC share (combined_post × gross_ctc / combined_pre)
        # — the splitting step used to compute Line 16a remaining-CTC.
        post_phaseout_ctc_share_usd=post_phaseout_ctc,
        refundable_actc_usd=refundable_actc,
        total_credit_usd=total_credit,
    )


def schedule_b_required_2025(
    *,
    interest_income_usd: Decimal,
    ordinary_dividends_usd: Decimal,
    has_foreign_account: bool,
) -> bool:
    """IRS Form 1040 Instructions / Schedule B precondition.

    Schedule B is required when interest > $1,500 OR dividends > $1,500
    OR a foreign account exists. The foreign-account trigger is
    independent of the $1,500 thresholds — Schedule B Part III is
    ALWAYS required for foreign accounts. For a U.S.-citizen-in-Germany
    posture with a Sparkasse / Comdirect / etc. account, this trigger
    is always set, so Schedule B is always rendered.
    """
    _require_non_negative(interest_income_usd, label="interest_income_usd")
    _require_non_negative(ordinary_dividends_usd, label="ordinary_dividends_usd")
    if has_foreign_account:
        return True
    if interest_income_usd > SCHEDULE_B_THRESHOLD_USD:
        return True
    if ordinary_dividends_usd > SCHEDULE_B_THRESHOLD_USD:
        return True
    return False


def schedule_b_parts_required_2025(
    *,
    interest_income_usd: Decimal,
    ordinary_dividends_usd: Decimal,
    has_foreign_account: bool,
) -> tuple[bool, bool, bool]:
    """Return (part_i_required, part_ii_required, part_iii_required).

    - Part I (Interest): required when interest > $1,500 OR a foreign
      account is present.
    - Part II (Dividends): required when dividends > $1,500.
    - Part III (Foreign Accounts): ALWAYS required when a foreign
      account exists, regardless of dollar thresholds.
    """
    _require_non_negative(interest_income_usd, label="interest_income_usd")
    _require_non_negative(ordinary_dividends_usd, label="ordinary_dividends_usd")
    part_i = (
        interest_income_usd > SCHEDULE_B_THRESHOLD_USD or has_foreign_account
    )
    part_ii = ordinary_dividends_usd > SCHEDULE_B_THRESHOLD_USD
    part_iii = has_foreign_account
    return part_i, part_ii, part_iii


def compute_us_assessment_2025(inputs: USAssessmentInputs2025) -> USOverallAssessment2025:
    # Phase 4 of the engine restructure: thin wrapper around the U.S. rule
    # graph. Legal arithmetic lives in tax_pipeline/y2025/us_rules.py per-stage
    # calculate functions for US25-00 through US25-21. Dataclass preserved as
    # typed view (option (i) per ENGINE-RESTRUCTURE-PLAN.md).
    from tax_pipeline.y2025.us_rules import (
        execute_us_rule_graph,
        us_assessment_from_final_facts,
        us_initial_facts_2025,
        us_initial_fingerprints_2025,
    )

    initial_facts = us_initial_facts_2025(inputs)
    execution = execute_us_rule_graph(
        initial_facts,
        input_fingerprints=us_initial_fingerprints_2025(initial_facts),
    )
    return us_assessment_from_final_facts(execution.final_facts, inputs=inputs)


