"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 1256 (Section 1256 contracts marked to market)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256&num=0&edition=prelim
contains:
  - § 1256(a)(3): statutory 60/40 character split — 60 % long-term
    capital gain / 40 % short-term capital gain on year-end mark-to-
    market gain or loss for § 1256 contracts.
  - The split helper ``section_1256_split_2025(total_usd)`` returns a
    ``(short_term, long_term)`` tuple in cents-rounded USD.
numeric_constants:
  - SECTION_1256_SHORT_RATIO: 0.40  # § 1256(a)(3) short-term character
  - SECTION_1256_LONG_RATIO: 0.60   # § 1256(a)(3) long-term character
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:7f65a524de2b63814c48635c041de251acda2d9bf612b1eb807c8dca55aa26d5
---
"""
# Shadow extraction of § 1256 mark-to-market 60/40 split (Phase 2
# leaf §). Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte.
#
# Authority: 26 U.S.C. § 1256(a)(3) — statutory 60 % long-term /
# 40 % short-term character split for § 1256 contracts (regulated
# futures, foreign-currency, dealer-equity-options, dealer-securities-
# futures, non-equity-options).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import round_cents

USC_1256_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1256&num=0&edition=prelim"
)

# 26 U.S.C. § 1256(a)(3) — statutory 40 % short-term / 60 % long-term
# character split for § 1256 contracts.
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SECTION_1256_SHORT_RATIO = _CONSTANTS["SECTION_1256_SHORT_RATIO"]
SECTION_1256_LONG_RATIO = _CONSTANTS["SECTION_1256_LONG_RATIO"]


def section_1256_split_2025(total_usd: Decimal) -> tuple[Decimal, Decimal]:
    """26 U.S.C. § 1256(a)(3) statutory 40/60 character split.

    Returns ``(short_term_usd, long_term_usd)`` in cents-rounded USD.
    Authority: 26 U.S.C. § 1256(a)(3).
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256
    """
    short_term = round_cents(total_usd * SECTION_1256_SHORT_RATIO)
    long_term = round_cents(total_usd * SECTION_1256_LONG_RATIO)
    return short_term, long_term


__all__ = (
    "USC_1256_URL",
    "SECTION_1256_SHORT_RATIO",
    "SECTION_1256_LONG_RATIO",
    "section_1256_split_2025",
)
