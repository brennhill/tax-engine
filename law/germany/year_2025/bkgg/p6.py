"""
---
jurisdiction: DE
tax_year: 2025
statute: § 6 BKGG (Bundeskindergeldgesetz) — Höhe des Kindergeldes
url: https://www.gesetze-im-internet.de/bkgg_1996/__6.html
contains:
  - § 6 Abs. 2 BKGG: monthly Kindergeld amount (€255 per child for 2025;
    €250 since 01.01.2023, raised to €255 from 01.01.2025; statutory
    uniform — no longer escalating with child count)
  - kindergeld_for_child_2025: per-child Kindergeld actually paid to *this*
    filer (taxpayer or spouse) under § 31 Satz 4 EStG; payments to the
    other parent are out of this filer's claim
numeric_constants:
  - KINDERGELD_2025_MONTHLY_EUR: 255  # § 6 Abs. 2 BKGG
  - KINDERGELD_2025_ANNUAL_EUR: 3060  # 12 × monthly
amended_by:
  - Inflationsausgleichsgesetz 2022 (Kindergeld €250 uniform since
    01.01.2023)
  - Steuerfortentwicklungsgesetz 2024 (BGBl. 2024 I, raised to
    €255/month effective 01.01.2025)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:8c92802d17a79a895f31323f0ba3943e6bc9defd4da2ddc6eaa6782a143f3924
---
"""
# Shadow extraction of § 6 BKGG (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# Bundeskindergeldgesetz § 6 Abs. 2: €250/month from 01.01.2023
# (Inflationsausgleichsgesetz 2022) raised to €255/month from 01.01.2025
# by the Steuerfortentwicklungsgesetz 2024 (BGBl. 2024 I). Uniform per
# child — no longer increasing with child count. Annual = €3,060 for a
# child eligible all twelve months.
# https://www.gesetze-im-internet.de/bkgg_1996/__6.html
# Statutory values live in the sibling p6.toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
KINDERGELD_2025_MONTHLY_EUR = _CONSTANTS["KINDERGELD_2025_MONTHLY_EUR"]
KINDERGELD_2025_ANNUAL_EUR = _CONSTANTS["KINDERGELD_2025_ANNUAL_EUR"]
# Closed enums for the per-child Kindergeld recipient field. The four
# values pair the statutory recipient categories with the engine's
# § 31 Satz 4 EStG gate (only payments to this filer count).
KINDERGELD_2025_RECIPIENT_VALUES = frozenset(
    {"taxpayer", "spouse", "other_parent", "none"}
)
KINDERGELD_2025_THIS_FILER_RECIPIENTS = frozenset({"taxpayer", "spouse"})


def kindergeld_for_child_2025(
    months_in_household: int,
    kindergeld_recipient: str,
) -> Decimal:
    """Per-child Kindergeld received during the year (BKGG since 2023).

    Only Kindergeld actually paid out to *this* filer (taxpayer or
    spouse) counts for the § 31 EStG Günstigerprüfung; payments to the
    other parent fall outside this filer's claim per § 31 Satz 4 EStG.

    Authority:
    - § 6 Abs. 2 BKGG (€255/month from 01.01.2025; was €250 since
      01.01.2023, raised by the Steuerfortentwicklungsgesetz 2024):
      https://www.gesetze-im-internet.de/bkgg_1996/__6.html
    - § 31 Satz 4 EStG (Kindergeld counted only to the entitled parent):
      https://www.gesetze-im-internet.de/estg/__31.html
    """
    if months_in_household < 0 or months_in_household > 12:
        raise ValueError(
            "months_in_household must be in [0, 12] for Kindergeld."
        )
    if kindergeld_recipient not in KINDERGELD_2025_RECIPIENT_VALUES:
        raise ValueError(
            f"Unsupported kindergeld_recipient: {kindergeld_recipient!r} "
            "(allowed: taxpayer, spouse, other_parent, none)."
        )
    if kindergeld_recipient not in KINDERGELD_2025_THIS_FILER_RECIPIENTS:
        return D("0.00")
    return q2(KINDERGELD_2025_MONTHLY_EUR * D(months_in_household))
