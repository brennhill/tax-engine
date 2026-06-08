"""
---
jurisdiction: DE
tax_year: 2025
statute: § 32d EStG (Abgeltungsteuer auf Kapitalerträge)
url: https://www.gesetze-im-internet.de/estg/__32d.html
contains:
  - § 32d Abs. 1 Satz 1 EStG: 25 % flat capital-income tax (Abgeltungsteuer)
  - § 32d Abs. 5 EStG: per-item foreign-tax credit cap on Auslandskapitalerträge
  - § 32d Abs. 6 EStG: Günstigerprüfung Antrag (project-internal materiality threshold)
numeric_constants:
  - CAPITAL_TAX_RATE_2025: 0.25
  - GUENSTIGERPRUEFUNG_MATERIALITY_EUR: 10.00 (project-internal)
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:cc1ff4c9faea47f3edf0bd9ced0df62e7e267c3f4e993c55efc78649207b062d
---
"""
# Shadow extraction of § 32d EStG (Phase 3 composing §). The
# CapitalTaxAssessment2025 / TreatyRelievedCapitalTax2025 dataclasses
# remain in the production module (Phase 6 will move types to
# law/germany/year_2025/types.py). Here we shadow the statutory
# tax/credit/cap arithmetic.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import floor_cent, q2
from tax_pipeline.y2025.germany_law import (
    CapitalTaxAssessment2025,
    TreatyRelievedCapitalTax2025,
)

D = Decimal

# § 32d Abs. 1 Satz 1 EStG: 25% flat capital-income tax (Abgeltungsteuer).
# https://www.gesetze-im-internet.de/estg/__32d.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
CAPITAL_TAX_RATE_2025 = _CONSTANTS["CAPITAL_TAX_RATE_2025"]

# F-DE-2 (audit-only): § 32d Abs. 6 EStG Günstigerprüfung shadow comparison
# threshold. Project-internal materiality, NOT a statutory amount.
# Authority context: § 32d Abs. 6 EStG (Antragsveranlagung):
# https://www.gesetze-im-internet.de/estg/__32d.html
GUENSTIGERPRUEFUNG_MATERIALITY_EUR = _CONSTANTS["GUENSTIGERPRUEFUNG_MATERIALITY_EUR"]


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def _require_unit_interval(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00") or value > D("1.00"):
        raise ValueError(f"{label} must be between 0 and 1 inclusive.")
    return value


def foreign_tax_credit_32d5_cap_2025(
    foreign_tax_items: tuple[tuple[Decimal, Decimal, Decimal], ...],
    *,
    capital_tax_rate: Decimal,
) -> Decimal:
    """§ 32d Abs. 5 EStG per-item foreign-tax credit cap.

    Authority: § 32d Abs. 5 EStG.
    https://www.gesetze-im-internet.de/estg/__32d.html
    """
    # § 32d Abs. 5 EStG caps creditable foreign tax per individual taxable capital item
    # and reduces paid foreign tax by any refund/reduction entitlement before applying the cap.
    _require_unit_interval(capital_tax_rate, label="capital_tax_rate")
    total_credit = D("0.00")
    for taxable_income_eur, foreign_tax_paid_eur, refund_entitlement_eur in foreign_tax_items:
        _require_non_negative_decimal(taxable_income_eur, label="foreign taxable capital income")
        _require_non_negative_decimal(foreign_tax_paid_eur, label="foreign tax paid")
        _require_non_negative_decimal(refund_entitlement_eur, label="foreign tax refund entitlement")
        net_foreign_tax = max(D("0.00"), foreign_tax_paid_eur - refund_entitlement_eur)
        item_cap = taxable_income_eur * capital_tax_rate
        total_credit += min(net_foreign_tax, item_cap)
    return q2(total_credit)


def capital_tax_after_foreign_tax_credit_2025(
    taxable_capital_eur: Decimal,
    foreign_tax_credit_eur: Decimal,
    *,
    capital_tax_rate: Decimal,
    soli_rate: Decimal,
) -> CapitalTaxAssessment2025:
    """§ 32d Abs. 1 / Abs. 5 EStG capital tax with FTC, then SolzG soli.

    Authority: § 32d Abs. 1 EStG (25% flat); § 32d Abs. 5 EStG (FTC);
    SolzG § 4 (5.5% soli on remaining income tax).
    https://www.gesetze-im-internet.de/estg/__32d.html
    """
    # Fix: model the statutory order explicitly.
    # § 32d Abs. 1 EStG applies the 25% capital-income tax first, § 32d Abs. 5 EStG credits
    # qualifying foreign tax next, and only the remaining income-tax assessment base is
    # subject to SolzG § 4.
    _require_non_negative_decimal(taxable_capital_eur, label="taxable_capital_eur")
    _require_non_negative_decimal(foreign_tax_credit_eur, label="foreign_tax_credit_eur")
    gross_income_tax = q2(taxable_capital_eur * capital_tax_rate)
    foreign_tax_credit = q2(min(foreign_tax_credit_eur, gross_income_tax))
    income_tax_after_foreign_credit = q2(max(D("0.00"), gross_income_tax - foreign_tax_credit))
    solidarity_surcharge = floor_cent(income_tax_after_foreign_credit * soli_rate)
    total_tax = q2(income_tax_after_foreign_credit + solidarity_surcharge)
    return CapitalTaxAssessment2025(
        taxable_capital_eur=q2(taxable_capital_eur),
        gross_income_tax_eur=gross_income_tax,
        foreign_tax_credit_eur=foreign_tax_credit,
        income_tax_after_foreign_credit_eur=income_tax_after_foreign_credit,
        solidarity_surcharge_eur=solidarity_surcharge,
        total_tax_eur=total_tax,
    )


def treaty_relieved_capital_tax_2025(
    income_tax_after_foreign_credit_eur: Decimal,
    solidarity_surcharge_before_treaty_eur: Decimal,
    treaty_credit_eur: Decimal,
) -> TreatyRelievedCapitalTax2025:
    """§ 5 SolzG 1995 ordering for treaty credits (soli first, then income tax).

    Authority: § 5 SolzG 1995.
    https://www.gesetze-im-internet.de/solzg_1995/__5.html
    """
    # Fix: make the treaty-credit ordering auditable.
    # § 5 SolzG 1995 applies the relief against soli first and only then against the
    # remaining income tax.
    _require_non_negative_decimal(income_tax_after_foreign_credit_eur, label="income_tax_after_foreign_credit_eur")
    _require_non_negative_decimal(solidarity_surcharge_before_treaty_eur, label="solidarity_surcharge_before_treaty_eur")
    _require_non_negative_decimal(treaty_credit_eur, label="treaty_credit_eur")
    treaty_credit = q2(max(treaty_credit_eur, D("0.00")))
    if treaty_credit != D("0.00"):
        raise NotImplementedError(
            "Manual Germany treaty dividend credits are not supported as a separate second capital credit. "
            "Credit foreign tax through the § 32d(5) per-item cap instead."
        )
    solidarity_after_treaty = q2(max(D("0.00"), solidarity_surcharge_before_treaty_eur - treaty_credit))
    remaining_credit = q2(max(D("0.00"), treaty_credit - solidarity_surcharge_before_treaty_eur))
    income_tax_after_treaty = q2(max(D("0.00"), income_tax_after_foreign_credit_eur - remaining_credit))
    return TreatyRelievedCapitalTax2025(
        treaty_credit_eur=treaty_credit,
        solidarity_surcharge_before_treaty_eur=q2(solidarity_surcharge_before_treaty_eur),
        solidarity_surcharge_after_treaty_eur=solidarity_after_treaty,
        income_tax_before_treaty_eur=q2(income_tax_after_foreign_credit_eur),
        income_tax_after_treaty_eur=income_tax_after_treaty,
        total_tax_after_treaty_eur=q2(income_tax_after_treaty + solidarity_after_treaty),
    )
