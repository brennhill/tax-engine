"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 901 (Foreign Tax Credit — credit allowed)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
contains:
  - § 901(a): allowance of credit for foreign income taxes paid or
    accrued. The allowed-credit selection helper
    ``allowed_ftc_2025(limitation, current_year, carryover)`` returns
    ``min(limitation, current_year + carryover)``.
  - § 905(a): paid-basis election (cash-basis FTC). The companion URL
    constant ``USC_905_URL`` is preserved for the timing-posture
    references that consume it.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:8d02de8e06e3e89f8eb516b6be066bdc4cec1852d93f1f372e069c2944924748
---
"""
# Shadow extraction of § 901 FTC mechanism (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.us_law`` byte-for-byte. The § 904 limitation
# helper lives in ``p904.py``; this file owns the credit-allowance
# selection (current-year + carryover capped by the § 904 limitation).
#
# Authority: 26 U.S.C. § 901 — foreign tax credit allowed.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905
from __future__ import annotations

from decimal import Decimal

from law._utils.money import _require_non_negative, round_cents

USC_901_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section901&num=0&edition=prelim"
)
# § 905(a) — paid-basis FTC election. Default § 901 is accrued-basis;
# § 905(a) lets the taxpayer elect cash-basis (paid-when-paid) timing,
# binding for that year and every subsequent year until revoked.
USC_905_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section905&num=0&edition=prelim"
)


def allowed_ftc_2025(
    *,
    limitation_usd: Decimal,
    current_year_foreign_tax_usd: Decimal,
    carryover_usd: Decimal,
) -> tuple[Decimal, Decimal]:
    """26 U.S.C. § 901 / § 904 allowed-FTC selection.

    Returns ``(allowed, available)`` where:
      - ``available = current_year + carryover`` (§ 901 paid/accrued
        + § 904(c) carryover bucket)
      - ``allowed = min(limitation, available)`` (§ 904(a) per-basket
        limitation as the binding ceiling).

    Authority: 26 U.S.C. § 901(a); § 904(a)/(c).
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
    """
    _require_non_negative(limitation_usd, label="limitation_usd")
    _require_non_negative(current_year_foreign_tax_usd, label="current_year_foreign_tax_usd")
    _require_non_negative(carryover_usd, label="carryover_usd")
    available = round_cents(current_year_foreign_tax_usd + carryover_usd)
    return round_cents(min(limitation_usd, available)), available


__all__ = (
    "USC_901_URL",
    "USC_905_URL",
    "allowed_ftc_2025",
)
