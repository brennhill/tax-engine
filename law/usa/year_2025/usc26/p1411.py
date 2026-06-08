"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 1411 (Net Investment Income Tax)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411&num=0&edition=prelim
contains:
  - § 1411(a): 3.8 % NIIT on the lesser of net investment income (NII)
    and the excess of MAGI over the filing-status threshold.
  - § 1411(b): NIIT thresholds — $200,000 (Single/HoH), $250,000 (MFJ),
    $125,000 (MFS). Statutory; NOT inflation-indexed. The thresholds
    are loaded per filing posture into ``USTaxConstants2025.niit_threshold_usd``,
    so the assessment helper accepts the threshold as a parameter.
  - § 1411(d)(1)(A): MAGI add-back of the § 911 excluded amount for
    NIIT purposes. The add-back itself is computed in the § 911 file
    (``p911.py``) and feeds the MAGI input to the assessment helper
    here at the rule layer.
numeric_constants:
  - NIIT_RATE: 0.038  # § 1411(a) statutory rate
imports_from:
  - law/usa/year_2025/usc26/p911.py: § 911 / § 1411(d)(1)(A) MAGI
    add-back of the FEIE excluded amount for NIIT
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:63979adb9f51eb7290b80a9e7e637a46bf78b12bca9aa33b84c2f86459583a44
---
"""
# Shadow extraction of § 1411 NIIT (Phase 3 composing §). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The 3.8 % rate is
# statutory; the filing-status thresholds are likewise statutory but
# loaded onto ``USTaxConstants2025`` per filing posture, so the helper
# accepts the threshold as a parameter rather than indexing into a
# filing-status switch here. The § 911 MAGI add-back is computed in
# ``p911.py`` (returned as ``USFEIEAssessment2025.niit_magi_addback_usd``)
# and added to AGI before this helper runs at the rule layer.
#
# Authority: 26 U.S.C. § 1411 — Net Investment Income Tax.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import round_cents

# Re-use production dataclass so equality holds against orig outputs.
from tax_pipeline.y2025.us_law import USNIITAssessment2025

USC_1411_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1411&num=0&edition=prelim"
)
IRS_I8960 = "https://www.irs.gov/instructions/i8960"

# 26 U.S.C. § 1411(a) — 3.8 % statutory NIIT rate.
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
NIIT_RATE = _CONSTANTS["NIIT_RATE"]


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
    # 26 U.S.C. § 1411 taxes the lesser of net investment income and MAGI
    # excess over the filing-status threshold.
    #
    # IMPORTANT — F-USLAW-5: ``adjusted_gross_income_usd`` is named "AGI"
    # but MUST be MAGI per § 1411(d)(1)(A): callers add back the § 911
    # excluded foreign earned income BEFORE invoking this function. The
    # FEIE assessment surfaces ``niit_magi_addback_usd`` exactly for this
    # purpose; passing raw AGI silently understates NIIT for FEIE-electing
    # filers. The shadow keeps the legacy parameter name to remain
    # byte-identical with production until the rename can be coordinated
    # across all callers.
    # https://www.law.cornell.edu/uscode/text/26/1411
    # The saved posture includes staking income in NII as an explicit manual position.
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


__all__ = (
    "USC_1411_URL",
    "IRS_I8960",
    "NIIT_RATE",
    "niit_assessment_2025",
)
