"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 1401 (Self-Employment Contributions Act tax)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401&num=0&edition=prelim
contains:
  - § 1401(a): 12.4 % OASDI on net SE earnings up to the SSA wage base.
  - § 1401(b)(1): 2.9 % Medicare on all net SE earnings.
  - § 1401(b)(2): additional 0.9 % Medicare tax above the § 3101(b)(2)
    threshold (the assessment helper for the 0.9 % portion is in
    ``p3101.py`` so wages and SE earnings can be combined per
    Form 8959 Part III).
  - § 1402(a)(12): only 92.35 % of net SE earnings is subject to SE tax
    (the residual 7.65 % approximates the employer-share deduction).
  - 2025 Social Security (OASDI) wage base: $176,100 (SSA Press Release
    2024-10-10).
  - § 164(f) one-half SE-tax deduction is consumed by ``p63``/AGI.
  - U.S.-Germany Totalization Agreement (1979) — when a German
    Certificate of Coverage applies, § 1401 does not attach. The shadow
    fails closed because the certificate path is not modeled.
numeric_constants:
  - SECA_NET_EARNINGS_FACTOR: 0.9235  # § 1402(a)(12)
  - OASDI_RATE: 0.124                 # § 1401(a)
  - MEDICARE_RATE: 0.029              # § 1401(b)(1)
  - SS_WAGE_BASE_2025_USD: 176100     # SSA 2024-10-10 (statutory cap)
  - EMPLOYEE_MEDICARE_RATE: 0.0145    # § 3101(b)(1) employee half
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:8c560f9cf2a582718bc4b6271a374dddad6c261b8df93306ca36ec704f3948d5
---
"""
# Shadow extraction of § 1401 SECA tax (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The § 1401(b)(2) 0.9 %
# Additional Medicare assessment lives in ``p3101.py`` so Form 8959
# Part III's combined wage/SE base can stay together.
#
# Authority: 26 U.S.C. § 1401 (SECA tax) + § 1402(a)(12) (net SE
# earnings factor); SSA wage-base announcement (statutory cap, not
# inflation-indexed in the IRC sense).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402
# https://www.ssa.gov/oact/cola/cbb.html
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import ZERO_USD, _require_non_negative, round_cents

# Re-use production dataclasses so shadow output instances compare
# equal to production output under unittest.assertEqual.
from tax_pipeline.y2025.us_law import (
    SSA_TOTALIZATION_DE_URL,
    USSelfEmploymentInputs2025,
    USSelfEmploymentTaxAssessment2025,
)

USC_1401_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1401&num=0&edition=prelim"
)
USC_1402_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1402&num=0&edition=prelim"
)
IRS_SCHEDULE_SE_URL = (
    "https://www.irs.gov/forms-pubs/about-schedule-se-form-1040"
)

# 26 U.S.C. § 1402(a)(12) — only 92.35 % of net SE earnings is subject
# to SE tax (the residual approximates the employer-share deduction).
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SECA_NET_EARNINGS_FACTOR = _CONSTANTS["SECA_NET_EARNINGS_FACTOR"]
# § 1401(a) — OASDI 12.4 % on net SE earnings up to SSA wage base.
OASDI_RATE = _CONSTANTS["OASDI_RATE"]
# § 1401(b)(1) — Medicare 2.9 % on all net SE earnings (employee
# 1.45 % × 2 = 2.9 %).
MEDICARE_RATE = _CONSTANTS["MEDICARE_RATE"]
# § 3101(b)(1) — employee Medicare half-rate (used by Form 8959
# wage-side computation that the assessment in ``p3101.py`` consumes).
EMPLOYEE_MEDICARE_RATE = _CONSTANTS["EMPLOYEE_MEDICARE_RATE"]
# 2025 Social Security (OASDI) wage base — SSA Press Release
# 2024-10-10. https://www.ssa.gov/oact/cola/cbb.html
SS_WAGE_BASE_2025_USD = _CONSTANTS["SS_WAGE_BASE_2025_USD"]


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
        separate ``additional_medicare_assessment_2025`` (``p3101.py``)
        so it can be combined with the wage-side computation per
        Form 8959.

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


__all__ = (
    "USC_1401_URL",
    "USC_1402_URL",
    "IRS_SCHEDULE_SE_URL",
    "SECA_NET_EARNINGS_FACTOR",
    "OASDI_RATE",
    "MEDICARE_RATE",
    "EMPLOYEE_MEDICARE_RATE",
    "SS_WAGE_BASE_2025_USD",
    "se_tax_assessment_2025",
)
