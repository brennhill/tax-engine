"""
---
jurisdiction: DE
tax_year: 2025
statute: § 24a EStG (Altersentlastungsbetrag)
url: https://www.gesetze-im-internet.de/estg/__24a.html
contains:
  - § 24a Satz 1, 3, 5 EStG: rate × eligible income capped at cohort cap
  - § 24a Satz 5 EStG Anlage: cohort table by year-turned-64
numeric_constants:
  - ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS: 64
  - ALTERSENTLASTUNGSBETRAG_2025_TABLE: {2005: (0.40, 1900), ..., 2025: (0.132, 627)}
amended_by:
  - Wachstumschancengesetz (28.03.2024, BGBl. I 2024 Nr. 108) — re-keyed Anlage from 2023 cohort
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:24c79c23fab5d2b59aea030f460d892e3389361430e567c100dd3c7c64f529a7
---
"""
# Shadow extraction of § 24a EStG (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_tables
from law._utils.money import q2

D = Decimal

# § 24a EStG Altersentlastungsbetrag — sliding scale keyed by the
# calendar year the taxpayer first turned 64 (Vollendung des 64.
# Lebensjahres). Once established, the (rate, cap) is fixed for life
# under § 24a Satz 5 EStG. The 2024-anchored rate of 11.2 % / €532
# carries forward to 2025. The Anlage below covers cohorts 2005-2025
# that may still apply to 2025 returns.
# https://www.gesetze-im-internet.de/estg/__24a.html
# Statutory Anlage lives in the sibling .toml data file (W2.A / T1.2)
# under shape="dict_int_decimal_tuple". Year-on-year roll-forward
# (Wachstumschancengesetz, BGBl. I 2024 Nr. 108) edits the TOML, not
# this Python module.
_TABLES = load_tables(Path(__file__).with_suffix(".toml"))
ALTERSENTLASTUNGSBETRAG_2025_TABLE: dict[int, tuple[Decimal, Decimal]] = dict(
    _TABLES["ALTERSENTLASTUNGSBETRAG_2025_TABLE"]
)
ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS = 64


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def altersentlastungsbetrag_2025(
    *,
    birth_year: int,
    eligible_income_eur: Decimal,
    tax_year: int = 2025,
) -> Decimal:
    """§ 24a EStG Altersentlastungsbetrag for a single person.

    Authority: § 24a Sätze 1, 3, 5 EStG. Rate and cap are fixed for life
    by the calendar year in which the taxpayer first turned 64. Eligible
    income excludes § 19 wages and Beamtenversorgung pensions
    (§ 24a Satz 2 Nr. 1 EStG).
    https://www.gesetze-im-internet.de/estg/__24a.html
    """
    # § 24a Satz 1, 3, 5 EStG: an Altersentlastungsbetrag of (rate × eligible
    # income) capped at the cohort cap is granted to taxpayers who turned
    # 64 BEFORE the start of the assessment year. Rate and cap are fixed for
    # life by the calendar year in which the taxpayer first met the age
    # threshold (Vollendung des 64. Lebensjahres) per § 24a Satz 5 EStG.
    if birth_year <= 0:
        return D("0.00")
    _require_non_negative_decimal(eligible_income_eur, label="eligible_income_eur")
    year_turned_64 = birth_year + ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS
    if year_turned_64 >= tax_year:
        # § 24a Satz 3 EStG: the allowance applies starting the assessment
        # year following the year the taxpayer turned 64. A taxpayer who
        # turns 64 during 2025 first qualifies in 2026.
        return D("0.00")
    if year_turned_64 not in ALTERSENTLASTUNGSBETRAG_2025_TABLE:
        # Use the closest cohort year covered by the official Anlage; for
        # taxpayers who turned 64 before 2005 the rate-pair is the 2005 row.
        cohort_year = max(
            min(year_turned_64, max(ALTERSENTLASTUNGSBETRAG_2025_TABLE)),
            min(ALTERSENTLASTUNGSBETRAG_2025_TABLE),
        )
    else:
        cohort_year = year_turned_64
    rate, cap = ALTERSENTLASTUNGSBETRAG_2025_TABLE[cohort_year]
    return q2(min(cap, q2(eligible_income_eur * rate)))
