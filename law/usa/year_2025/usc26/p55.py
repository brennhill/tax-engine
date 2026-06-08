"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 55 (Alternative Minimum Tax — imposition + tentative computation)
url: https://www.law.cornell.edu/uscode/text/26/55
contains:
  - § 55(a): AMT = max(0, tentative_min_tax − AMTFTC − regular_tax_after_FTC)
  - § 55(b)(1): tentative minimum tax = 26 % × min(AMTI_excess, break)
    + 28 % × max(0, AMTI_excess − break). § 55(b)(1)(A)(ii)(II) halves
    the rate-break for MFS.
  - § 55(b)(3): preserves § 1(h) preferential capital-gain / qualified-
    dividend rates inside AMT (so the tentative minimum splits the AMTI
    base into ordinary + preferential and runs a § 1(h)-style QDCGTW
    on the preferential portion).
  - § 55(d): exemption amounts + phase-out start (Rev. Proc. 2024-40
    inflation amounts imported from ``rev_proc/proc_2024_40/p3_11.py``).
  - § 55(d)(3): exemption reduced by 25 cents per dollar of AMTI above
    the phase-out start.
numeric_constants:
  - AMT_PHASEOUT_RATE: 0.25  # § 55(d)(3) statutory reduction rate
  - AMT_RATE_LOW: 0.26       # § 55(b)(1)(A)(i) statutory low rate
  - AMT_RATE_HIGH: 0.28      # § 55(b)(1)(A)(ii) statutory high rate
imports_from:
  - law/usa/year_2025/rev_proc/proc_2024_40/p3_11.py:
      AMT_EXEMPTION_*, AMT_PHASEOUT_START_*, AMT_RATE_BREAK_*
  - law/usa/year_2025/usc26/p1.py:
      QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE,
      QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:90bcfec766739286f1ce57103508eb21e90c6a01db9cb67fdd6f076d93d5ede8
---
"""
# Shadow extraction of § 55 AMT (Phase 3 composing §). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The 2025 inflation
# amounts (exemption, phase-out start, rate break) are imported from
# Rev. Proc. 2024-40 § 3.11 (``rev_proc/proc_2024_40/p3_11.py``); the
# § 55(d)(3) phase-out rate (0.25) and § 55(b)(1) rate constants
# (26 %, 28 %) are statutory and live here. The § 1(h) preferential
# rates referenced by § 55(b)(3) come from § 1's file (``p1.py``).
#
# Authority: 26 U.S.C. § 55 — Alternative Minimum Tax.
# https://www.law.cornell.edu/uscode/text/26/55
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import ZERO_USD, _require_non_negative, round_cents
from law.usa.year_2025.rev_proc.proc_2024_40.p3_11 import (
    AMT_EXEMPTION_MFJ_2025_USD,
    AMT_EXEMPTION_MFS_2025_USD,
    AMT_EXEMPTION_SINGLE_2025_USD,
    AMT_PHASEOUT_START_MFJ_2025_USD,
    AMT_PHASEOUT_START_MFS_2025_USD,
    AMT_PHASEOUT_START_SINGLE_2025_USD,
    AMT_RATE_BREAK_2025_USD,
    AMT_RATE_BREAK_MFS_2025_USD,
)
from law.usa.year_2025.usc26.p1 import (
    QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE,
    QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE,
)

# Re-use production dataclasses so shadow output instances compare
# equal to production output under unittest.assertEqual.
from tax_pipeline.y2025.us_law import USTaxConstants2025

USC_55_URL = "https://www.law.cornell.edu/uscode/text/26/55"
FORM_6251_INSTRUCTIONS_URL = (
    "https://www.irs.gov/forms-pubs/about-form-6251"
)
REV_PROC_2024_40_URL = "https://www.irs.gov/pub/irs-drop/rp-24-40.pdf"

# § 55(d)(3) reduction rate: $0.25 of exemption lost per $1.00 of AMTI excess.
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
AMT_PHASEOUT_RATE = _CONSTANTS["AMT_PHASEOUT_RATE"]
# § 55(b)(1) statutory tentative-minimum-tax rates.
AMT_RATE_LOW = _CONSTANTS["AMT_RATE_LOW"]
AMT_RATE_HIGH = _CONSTANTS["AMT_RATE_HIGH"]


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


__all__ = (
    "USC_55_URL",
    "FORM_6251_INSTRUCTIONS_URL",
    "REV_PROC_2024_40_URL",
    "AMT_PHASEOUT_RATE",
    "AMT_RATE_LOW",
    "AMT_RATE_HIGH",
    "amt_exemption_after_phaseout_2025",
    "amt_tentative_minimum_tax_2025",
    "amt_owed_2025",
)
