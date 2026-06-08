"""
---
jurisdiction: DE
tax_year: 2025
statute: § 33 EStG (außergewöhnliche Belastungen)
url: https://www.gesetze-im-internet.de/estg/__33.html
contains:
  - § 33 Abs. 1 EStG: deduction = max(0, expenses − zumutbare Belastung)
  - § 33 Abs. 3 EStG: zumutbare Belastung sliding scale (slab method per BFH VI R 75/14)
numeric_constants:
  - ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR: (15340.00, 51130.00)
  - ZUMUTBARE_BELASTUNG_2025_RATES (single_no_children, joint_or_few_children, many_children)
amended_by: []
case_law:
  - BFH VI R 75/14 (19.01.2017): slab progression on the brackets, not slab-replacement
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:8ad247dc46b279fbb2613c3bebd6c480d6dc6eb5941232a9220f8b94123e4bc4
---
"""
# Shadow extraction of § 33 EStG (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_tables
from law._utils.money import q2

D = Decimal

# § 33 Abs. 3 EStG zumutbare Belastung sliding scale, applied progressively
# (slab method per BFH VI R 75/14, 19.01.2017): each income tier's rate
# applies only to the income band within that tier. Family categories per
# § 33 Abs. 3 Satz 1 EStG:
# - "single_no_children": single (or married-separate) without children,
# - "joint_or_few_children": married/joint without children OR single with
#   1-2 dependent children,
# - "many_children": three or more dependent children regardless of posture.
# https://www.gesetze-im-internet.de/estg/__33.html
# Statutory schedule lives in the sibling .toml data file (W2.A / T1.2):
# a single ``bracket_list`` table with one row per income band carries
# both the upper-threshold (Decimal("Infinity") for the unbounded top
# band) and the per-family-category rate. The legacy
# ``BRACKETS_EUR`` / ``RATES`` split is reconstructed from that one
# table so existing call sites keep their imports unchanged.
_TABLES = load_tables(Path(__file__).with_suffix(".toml"))
_ZUMUTBARE_BELASTUNG_2025_BRACKET_ROWS = _TABLES["ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR"]
_ZUMUTBARE_BELASTUNG_2025_CATEGORIES = (
    "single_no_children",
    "joint_or_few_children",
    "many_children",
)
ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR: tuple[Decimal, Decimal] = tuple(
    row["upper_threshold"]
    for row in _ZUMUTBARE_BELASTUNG_2025_BRACKET_ROWS
    if row["upper_threshold"].is_finite()
)
ZUMUTBARE_BELASTUNG_2025_RATES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    category: tuple(row[category] for row in _ZUMUTBARE_BELASTUNG_2025_BRACKET_ROWS)
    for category in _ZUMUTBARE_BELASTUNG_2025_CATEGORIES
}


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def zumutbare_belastung_2025(
    *,
    gesamtbetrag_der_einkuenfte_eur: Decimal,
    family_category: str,
) -> Decimal:
    """§ 33 Abs. 3 EStG zumutbare Belastung (slab progression).

    BFH VI R 75/14 (19.01.2017) confirms slab progression: each tier's
    rate applies only to the band within that tier (not slab-replacement).

    Authority: § 33 Abs. 3 EStG; BFH VI R 75/14.
    https://www.gesetze-im-internet.de/estg/__33.html
    """
    # § 33 Abs. 3 EStG progressive (slab) computation per BFH VI R 75/14
    # (19.01.2017): each tier rate applies only to the band within that
    # tier. The thresholds are 15 340 EUR and 51 130 EUR; the bracket
    # rates depend on family category.
    _require_non_negative_decimal(
        gesamtbetrag_der_einkuenfte_eur, label="gesamtbetrag_der_einkuenfte_eur"
    )
    if family_category not in ZUMUTBARE_BELASTUNG_2025_RATES:
        raise ValueError(
            "Unsupported zumutbare_belastung_family_category "
            f"{family_category!r}; expected one of "
            f"{sorted(ZUMUTBARE_BELASTUNG_2025_RATES)}."
        )
    bracket_a, bracket_b = ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR
    rate_a, rate_b, rate_c = ZUMUTBARE_BELASTUNG_2025_RATES[family_category]
    income = gesamtbetrag_der_einkuenfte_eur
    band_a = min(income, bracket_a)
    band_b = max(D("0.00"), min(income, bracket_b) - bracket_a)
    band_c = max(D("0.00"), income - bracket_b)
    burden = band_a * rate_a + band_b * rate_b + band_c * rate_c
    return q2(burden)


def aussergewoehnliche_belastungen_deductible_2025(
    *,
    medical_expenses_eur: Decimal,
    gesamtbetrag_der_einkuenfte_eur: Decimal,
    family_category: str,
) -> tuple[Decimal, Decimal]:
    """§ 33 Abs. 1 / Abs. 3 EStG: deductible = max(0, expenses − zumutbare Belastung).

    Returns ``(deductible, zumutbare_belastung)`` so the per-stage trace
    can show both legs.

    Authority: § 33 Abs. 1 / Abs. 3 EStG.
    https://www.gesetze-im-internet.de/estg/__33.html
    """
    # § 33 Abs. 1 / Abs. 3 EStG: deductible außergewöhnliche Belastungen =
    # max(0, claimed expenses − zumutbare Belastung). Returns
    # (deductible, zumutbare_belastung) so the per-stage trace can show
    # both legs.
    _require_non_negative_decimal(medical_expenses_eur, label="medical_expenses_eur")
    burden = zumutbare_belastung_2025(
        gesamtbetrag_der_einkuenfte_eur=gesamtbetrag_der_einkuenfte_eur,
        family_category=family_category,
    )
    deductible = q2(max(D("0.00"), medical_expenses_eur - burden))
    return deductible, burden
