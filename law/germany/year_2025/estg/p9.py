"""
---
jurisdiction: DE
tax_year: 2025
statute: § 9 EStG (Werbungskosten)
url: https://www.gesetze-im-internet.de/estg/__9.html
contains:
  - § 9 Abs. 5 EStG: cross-reference to § 4 Abs. 5 Satz 1 Nr. 6c EStG
    Tagespauschale (home-office daily rate / annual cap)
numeric_constants:
  - HOME_OFFICE_DAILY_RATE_EUR: 6.00  # § 4 Abs. 5 Satz 1 Nr. 6c EStG
  - HOME_OFFICE_MAX_EUR: 1260.00      # § 4 Abs. 5 Satz 1 Nr. 6c EStG annual cap
amended_by:
  - Jahressteuergesetz 2022 (BGBl. I 2022 S. 2294) — Tagespauschale rate to €6
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:0bdfdd571bc2c8b3b0f39b412ada3a00dc32d56780f9397758f14530ecf2744d
---
"""
# Shadow extraction of § 9 EStG Werbungskosten (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte. The original file is
# unchanged; tests still pass against it. Identity tests in ``p9_test.py``
# assert the constants and function output equal the production module.
#
# Authority: § 9 EStG (Werbungskosten); the actual Tagespauschale rate +
# annual cap live at § 4 Abs. 5 Satz 1 Nr. 6c EStG and apply by
# § 9 Abs. 5 EStG cross-reference for employee Werbungskosten.
# https://www.gesetze-im-internet.de/estg/__9.html
# https://www.gesetze-im-internet.de/estg/__4.html
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# § 4 Abs. 5 Satz 1 Nr. 6c EStG: €6 daily rate for the home-office
# Tagespauschale, applied via § 9 Abs. 5 EStG to employee Werbungskosten.
# https://www.gesetze-im-internet.de/estg/__4.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
HOME_OFFICE_DAILY_RATE_EUR = _CONSTANTS["HOME_OFFICE_DAILY_RATE_EUR"]

# § 4 Abs. 5 Satz 1 Nr. 6c EStG: €1,260 annual cap on the Tagespauschale
# (210 days × €6).
# https://www.gesetze-im-internet.de/estg/__4.html
HOME_OFFICE_MAX_EUR = _CONSTANTS["HOME_OFFICE_MAX_EUR"]


def _require_non_negative_int(value: int, *, label: str) -> int:
    if value < 0:
        raise ValueError(f"{label} must be non-negative.")
    return value


def home_office_tagespauschale_2025(
    days_without_first_workplace_visit: int,
    days_with_first_workplace_visit: int,
    *,
    visit_days_no_other_workplace: bool = False,
) -> Decimal:
    """§ 4 Abs. 5 Satz 1 Nr. 6c EStG / § 9 Abs. 5 EStG home-office Tagespauschale.

    Returns the deductible Tagespauschale amount: ``min(eligible_days × €6,
    €1,260)``. Days with a first-workplace visit only qualify when the
    taxpayer has no other workplace available that day (§ 4 Abs. 5
    Satz 1 Nr. 6c Satz 2 EStG).

    Authority: § 4 Abs. 5 Satz 1 Nr. 6c EStG (rate + cap), § 9 Abs. 5
    EStG (cross-reference for Werbungskosten side).
    https://www.gesetze-im-internet.de/estg/__4.html
    https://www.gesetze-im-internet.de/estg/__9.html
    """
    # Fix: keep the home-office cap in one helper so every caller uses the same § 4 Abs. 5
    # Satz 1 Nr. 6c EStG / § 9 Abs. 5 EStG daily-rate and annual-cap rule.
    _require_non_negative_int(days_without_first_workplace_visit, label="days_without_first_workplace_visit")
    _require_non_negative_int(days_with_first_workplace_visit, label="days_with_first_workplace_visit")
    if days_with_first_workplace_visit and not visit_days_no_other_workplace:
        raise ValueError(
            "Home-office days with a first-workplace visit require an explicit no other workplace position."
        )
    eligible_days = days_without_first_workplace_visit + days_with_first_workplace_visit
    return q2(min(D(eligible_days) * HOME_OFFICE_DAILY_RATE_EUR, HOME_OFFICE_MAX_EUR))
