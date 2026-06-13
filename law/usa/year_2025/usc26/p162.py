"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 162 (Trade or business expenses) + § 61 (Gross income)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162&num=0&edition=prelim
contains:
  - § 61(a)(2): gross income derived from business (Schedule C line 7 —
    IRS-VERIFIED 2026-06-13 against https://www.irs.gov/pub/irs-pdf/f1040sc.pdf).
  - § 162(a): ordinary & necessary trade-or-business expenses are
    deductible (Schedule C line 28 — total expenses).
  - Schedule C (Form 1040) net profit (line 31) = gross income (line 7)
    − total expenses (line 28) in the no-home-office posture; the netting
    is constant-free. A loss is NOT floored on Schedule C itself — the
    signed net is what reaches Form 1040 (Schedule 1 line 3) and
    Schedule SE line 2.
  - 26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c): the QBI deduction requires
    income effectively connected with a trade or business WITHIN the
    United States. Foreign-source business income is NOT QBI, so the
    § 199A deduction is not_applicable (zero) for the engine's taxpayer
    (a U.S. citizen resident in Germany). ``qbi_gate_2025`` returns the
    cited not_applicable status and fails closed on the
    us_effectively_connected QBI-granting path (not modeled).
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-8
audited_on: 2026-06-13
audit_hash: sha256:49db684fa6491bc59e744c6045f2006eb2cc0f294c490b09da91a17daf511ca3
---
"""
# Shadow extraction of § 61 / § 162 Schedule C netting + the § 199A
# applicability gate (Phase 2 freelancer support). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte: the netting is constant-free
# (no .toml sibling), so this file re-exports the production dataclasses and
# functions and asserts identity in ``p162_test.py``.
#
# Authority: 26 U.S.C. § 61 (gross income) + § 162 (trade-or-business
# expenses); 26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c) (QBI requires
# US-effectively-connected income). IRS Schedule C (Form 1040).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A
# https://www.irs.gov/forms-pubs/about-schedule-c-form-1040
from __future__ import annotations

# Re-use production dataclasses + functions so shadow output instances compare
# equal to production output under unittest.assertEqual (the byte-for-byte
# identity contract enforced in p162_test.py).
from tax_pipeline.y2025.us_law import (
    BUSINESS_INCOME_SOURCE_FOREIGN,
    BUSINESS_INCOME_SOURCE_US_EFFECTIVELY_CONNECTED,
    BUSINESS_INCOME_SOURCES,
    IRS_SCHEDULE_C_URL,
    QBI_GATE_BASIS_FOREIGN_NOT_APPLICABLE,
    QBI_GATE_STATUS_NOT_APPLICABLE,
    USQBIGateAssessment2025,
    USScheduleCInputs2025,
    USScheduleCResult2025,
    qbi_gate_2025,
    schedule_c_net_profit_2025,
)

USC_61_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section61&num=0&edition=prelim"
)
USC_162_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section162&num=0&edition=prelim"
)
USC_199A_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section199A&num=0&edition=prelim"
)
USC_864_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section864&num=0&edition=prelim"
)


__all__ = (
    "USC_61_URL",
    "USC_162_URL",
    "USC_199A_URL",
    "USC_864_URL",
    "IRS_SCHEDULE_C_URL",
    "BUSINESS_INCOME_SOURCE_FOREIGN",
    "BUSINESS_INCOME_SOURCE_US_EFFECTIVELY_CONNECTED",
    "BUSINESS_INCOME_SOURCES",
    "QBI_GATE_BASIS_FOREIGN_NOT_APPLICABLE",
    "QBI_GATE_STATUS_NOT_APPLICABLE",
    "USScheduleCInputs2025",
    "USScheduleCResult2025",
    "USQBIGateAssessment2025",
    "schedule_c_net_profit_2025",
    "qbi_gate_2025",
)
