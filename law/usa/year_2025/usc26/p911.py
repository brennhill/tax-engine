"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 911 (Foreign Earned Income Exclusion)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911&num=0&edition=prelim
contains:
  - § 911(b)(2)(D): annual FEIE ceiling (2025: $130,000 — imported from
    Rev. Proc. 2024-40 § 3.34, see ``rev_proc/proc_2024_40/p3_34.py``).
  - § 911(c)(1)(B): housing base amount = 16 % of FEIE ceiling
    (statutory rate, ``SECTION_911_HOUSING_BASE_RATE``).
  - § 911(c)(2)(A): housing-cost ceiling = 30 % of FEIE
    (``SECTION_911_HOUSING_CEILING_RATE``) before IRS Notice 2024-77
    location adjustment.
  - § 911(c)(4): self-employed routes housing amount to deduction.
  - § 911(d)(1)(A)/(B): bona-fide-residence / physical-presence tests.
  - § 911(d)(6): denial of FTC on tax allocable to excluded income.
  - § 1411(d)(1)(A) MAGI add-back of excluded income for NIIT (consumed
    here as ``niit_magi_addback_usd`` so § 1411 imports from this file).
numeric_constants:
  - SECTION_911_HOUSING_BASE_RATE: 0.16  # § 911(c)(1)(B)
  - SECTION_911_HOUSING_CEILING_RATE: 0.30  # § 911(c)(2)(A)
imports_from:
  - law/usa/year_2025/rev_proc/proc_2024_40/p3_34.py: SECTION_911_FEIE_2025_USD
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:a6b4bfa36c8fe87c7e59fe3a1eedcfe0703bff4268a7fc400526feb269841889
---
"""
# Shadow extraction of § 911 FEIE / housing exclusion / housing
# deduction (Phase 2 leaf §). Mirrors ``tax_pipeline.y2025.us_law``
# byte-for-byte. The 2025 FEIE ceiling ($130,000) is imported from the
# Rev. Proc. 2024-40 § 3.34 inflation table; the 16 % base / 30 %
# ceiling rates are statutory and live here.
#
# Authority: 26 U.S.C. § 911 — Foreign Earned Income Exclusion and
# § 911(c) housing exclusion / deduction. § 911(d)(6) denies FTC on
# tax allocable to the excluded amount; § 1411(d)(1)(A) requires the
# excluded amount to be added back to MAGI for NIIT purposes.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
# https://www.irs.gov/publications/p54
# https://www.irs.gov/forms-pubs/about-form-2555
# https://www.irs.gov/pub/irs-drop/n-24-77.pdf
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import ZERO_USD, _require_non_negative, round_cents
from law.usa.year_2025.rev_proc.proc_2024_40.p3_34 import (
    SECTION_911_FEIE_2025_USD,
)

# Re-use the production dataclasses so the shadow function returns
# instances that compare equal to the production function's outputs
# (USFEIEAssessment2025 is a frozen dataclass and equality is by class
# identity + field equality). Per LOCK.md § 6: dataclasses live at
# ``law/<jurisdiction>/<year>/types.py`` in the eventual end-state, but
# during Phase 2 leaf extraction we stay byte-identical with the
# production module by importing the dataclass rather than redeclaring.
from tax_pipeline.y2025.us_law import USFEIEAssessment2025, USFEIEInputs2025

USC_911_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section911&num=0&edition=prelim"
)
IRS_P54_URL = "https://www.irs.gov/publications/p54"
IRS_FORM_2555_URL = "https://www.irs.gov/forms-pubs/about-form-2555"
IRS_NOTICE_2024_77_URL = "https://www.irs.gov/pub/irs-drop/n-24-77.pdf"

# 26 U.S.C. § 911(c)(1)(B) — base housing amount = 16 % of FEIE ceiling
# (a statutory rate; not a Rev. Proc. inflation amount).
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SECTION_911_HOUSING_BASE_RATE = _CONSTANTS["SECTION_911_HOUSING_BASE_RATE"]
# 26 U.S.C. § 911(c)(2)(A) — housing-cost ceiling = 30 % of FEIE before
# IRS Notice 2024-77 location adjustment.
SECTION_911_HOUSING_CEILING_RATE = _CONSTANTS["SECTION_911_HOUSING_CEILING_RATE"]


# NOTE: USFEIEAssessment2025 is imported from tax_pipeline.y2025.us_law
# (see import block) so shadow output dataclasses compare equal to the
# production module's instances under unittest.assertEqual. The class
# definition is preserved verbatim there until Phase 6 moves dataclasses
# to ``law/usa/year_2025/types.py`` jurisdiction-wide.


def feie_assessment_2025(
    *,
    feie_inputs: USFEIEInputs2025,
) -> USFEIEAssessment2025:
    """Compute the § 911 / § 911(c) FEIE + housing exclusion / deduction.

    Authority:
      - 26 U.S.C. § 911(b)(2)(D) — annual exclusion ($130,000 for 2025
        per Rev. Proc. 2024-40 § 3.34).
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


__all__ = (
    "USC_911_URL",
    "IRS_P54_URL",
    "IRS_FORM_2555_URL",
    "IRS_NOTICE_2024_77_URL",
    "SECTION_911_FEIE_2025_USD",
    "SECTION_911_HOUSING_BASE_RATE",
    "SECTION_911_HOUSING_CEILING_RATE",
    "USFEIEAssessment2025",
    "feie_assessment_2025",
)
