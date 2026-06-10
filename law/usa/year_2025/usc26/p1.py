"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 1 (Tax imposed) — ordinary-income brackets
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
contains:
  - § 1 ordinary-income tax-rate schedule (10/12/22/24/32/35/37 brackets;
    the 2025 ceilings are loaded per filing posture from
    ``years/<year>/normalized/reference-data/us-tax-constants.csv`` into
    ``USTaxConstants2025.tax_bracket_*_ceiling_2025_usd``).
  - § 1(h) preferential 0/15/20 long-term-capital-gain and qualified-
    dividend rates: ``QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE = 15 %`` and
    ``QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE = 20 %``. The zero-rate band
    has no rate constant (the rate is 0).
  - IRS Form 1040 line-16 Tax Table lookup (``_tax_table_lookup_income_2025``),
    ``_tax_from_ordinary_brackets_2025``, ``tax_from_schedule_y2_2025``,
    ``tax_from_schedule_y2_2025_mfs`` and the § 1(h) Qualified Dividend
    and Capital Gain Tax Worksheet (``regular_tax_2025`` /
    ``regular_tax_2025_mfs``).
numeric_constants:
  - QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE: 0.15  # § 1(h)(1)(C)
  - QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE: 0.20   # § 1(h)(1)(D)
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:22c06e2c4698189adabc493ed7e6fc00a009b180bb8921cd91cf5d194f148a2a
---
"""
# Shadow extraction of § 1 ordinary-income brackets and § 1(h)
# preferential capital-gain / qualified-dividend rates (Phase 2 leaf §).
# Mirrors ``tax_pipeline.y2025.us_law`` byte-for-byte. The 2025 bracket
# ceilings are loaded per filing posture into ``USTaxConstants2025``
# rather than living as standalone constants here — that is consistent
# with the production module's posture-keyed bracket layout.
#
# Authority: 26 U.S.C. § 1 (ordinary-income brackets, including the
# § 1(h) preferential capital-gain rate schedule). Form 1040 line-16
# instructions and Pub. 550 specify the Tax Table / Computation
# Worksheet construction.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from pathlib import Path

from tax_pipeline.y2025.us_law import USTaxConstants2025

from law._utils.constants import load_constants
from law._utils.money import USD_CENT, ZERO_USD, _require_non_negative, round_cents

USC_1_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1&num=0&edition=prelim"
)

# IRC § 1(h)(1)(C) — qualified-dividend / long-term capital-gain 15 %
# bracket. Numerically coincident with DBA-USA Art. 10(2)(b) but legally
# independent (the treaty rate has its own constant in the treaty law
# module).
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE = _CONSTANTS["QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE"]
# IRC § 1(h)(1)(D) — qualified-dividend / long-term capital-gain 20 %
# bracket.
QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE = _CONSTANTS["QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE"]


def _tax_table_lookup_income_2025(taxable_ordinary_income: Decimal) -> Decimal:
    # IRS Form 1040 line-16 instructions require the Tax Table below $100,000.
    # The table's early rows are not uniform $50 buckets: 0-5 is zero-tax, 5-25
    # uses $10 rows, 25-3,000 uses $25 rows, and 3,000-100,000 uses $50 rows.
    if taxable_ordinary_income < Decimal("5.00"):
        return ZERO_USD
    if taxable_ordinary_income < Decimal("25.00"):
        row_start = Decimal("5.00") + (
            (taxable_ordinary_income - Decimal("5.00")) / Decimal("10.00")
        ).to_integral_value(rounding=ROUND_FLOOR) * Decimal("10.00")
        return row_start + Decimal("5.00")
    if taxable_ordinary_income < Decimal("3000.00"):
        row_start = Decimal("25.00") + (
            (taxable_ordinary_income - Decimal("25.00")) / Decimal("25.00")
        ).to_integral_value(rounding=ROUND_FLOOR) * Decimal("25.00")
        return row_start + Decimal("12.50")
    row_start = Decimal("3000.00") + (
        (taxable_ordinary_income - Decimal("3000.00")) / Decimal("50.00")
    ).to_integral_value(rounding=ROUND_FLOOR) * Decimal("50.00")
    return row_start + Decimal("25.00")


def _tax_from_ordinary_brackets_2025(
    taxable_ordinary_income: Decimal,
    constants: USTaxConstants2025,
) -> Decimal:
    thresholds = [
        Decimal("0.00"),
        constants.tax_bracket_10_ceiling_2025_usd,
        constants.tax_bracket_12_ceiling_2025_usd,
        constants.tax_bracket_22_ceiling_2025_usd,
        constants.tax_bracket_24_ceiling_2025_usd,
        constants.tax_bracket_32_ceiling_2025_usd,
        constants.tax_bracket_35_ceiling_2025_usd,
    ]
    rates = [Decimal("0.10"), Decimal("0.12"), Decimal("0.22"), Decimal("0.24"), Decimal("0.32"), Decimal("0.35"), Decimal("0.37")]
    base_taxes = [Decimal("0.00")]
    cumulative = Decimal("0.00")
    for idx, rate in enumerate(rates[:-1]):
        bracket_width = thresholds[idx + 1] - thresholds[idx]
        cumulative += bracket_width * rate
        base_taxes.append(cumulative)
    for idx, rate in enumerate(rates):
        low = thresholds[idx]
        high = thresholds[idx + 1] if idx + 1 < len(thresholds) else None
        if high is None or taxable_ordinary_income <= high:
            return base_taxes[idx] + (taxable_ordinary_income - low) * rate
    raise RuntimeError("unreachable 2025 tax schedule state")


def tax_from_schedule_y2_2025(
    taxable_ordinary_income: Decimal,
    constants: USTaxConstants2025,
) -> Decimal:
    # 26 U.S.C. § 1 imposes the ordinary-income tax. Form 1040 line-16 instructions require
    # the Tax Table for taxable income below $100,000; $100,000+ uses the computation worksheet.
    _require_non_negative(taxable_ordinary_income, label="taxable_ordinary_income")
    if taxable_ordinary_income == ZERO_USD:
        return ZERO_USD
    if taxable_ordinary_income < Decimal("100000.00"):
        table_income = _tax_table_lookup_income_2025(taxable_ordinary_income)
        table_tax = _tax_from_ordinary_brackets_2025(table_income, constants)
        return table_tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(USD_CENT)
    return _tax_from_ordinary_brackets_2025(taxable_ordinary_income, constants)


def tax_from_schedule_y2_2025_mfs(
    taxable_ordinary_income: Decimal,
    constants: USTaxConstants2025,
) -> Decimal:
    return tax_from_schedule_y2_2025(taxable_ordinary_income, constants)


__all__ = (
    "USC_1_URL",
    "QUALIFIED_DIVIDEND_FIFTEEN_BRACKET_RATE",
    "QUALIFIED_DIVIDEND_TWENTY_BRACKET_RATE",
    "_tax_table_lookup_income_2025",
    "_tax_from_ordinary_brackets_2025",
    "tax_from_schedule_y2_2025",
    "tax_from_schedule_y2_2025_mfs",
)
