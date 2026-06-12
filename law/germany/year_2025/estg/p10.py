"""
---
jurisdiction: DE
tax_year: 2025
statute: § 10 EStG (Sonderausgaben)
url: https://www.gesetze-im-internet.de/estg/__10.html
contains:
  - § 10 Abs. 1 Nr. 2 EStG: retirement Vorsorgeaufwendungen
  - § 10 Abs. 1 Nr. 3 EStG: basic health + nursing-care contributions
  - § 10 Abs. 1 Nr. 3a EStG: other Vorsorgeaufwendungen (employee + general caps)
  - § 10 Abs. 3 EStG: retirement Höchstbetrag (BBG knappschaftliche RV)
  - § 10 Abs. 4 EStG: §-Abs.-3a Vorsorge cap (€1,900 employee / €2,800 general)
  - § 10c EStG: Sonderausgaben-Pauschbetrag €36 / €72
numeric_constants:
  - RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR: 29344.00
  - OTHER_VORSORGE_CAP_EMPLOYEE_EUR: 1900.00
  - OTHER_VORSORGE_CAP_GENERAL_EUR: 2800.00
  - SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR: 36.00
  - SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR: 72.00
  - STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE: 0.04
amended_by:
  - Sozialversicherungs-Rechengrößenverordnung 2025 (BMAS) — BBG knappschaftliche RV €118,800
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:6ffdbae73b1c55cabe948d47493540518f9ec02a7a185c4380ab466071e01ab3
---
"""
# Shadow extraction of § 10 EStG Sonderausgaben (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants
from law._utils.money import q2

D = Decimal

# § 10 Abs. 4 EStG: alternate caps for "andere Vorsorgeaufwendungen"
# (Vorsorge other than retirement / basic health):
# - €1,900 for employees with statutory KV/PV cover (Satz 1).
# - €2,800 for self-employed and others without employer KV (Satz 2).
# https://www.gesetze-im-internet.de/estg/__10.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
OTHER_VORSORGE_CAP_EMPLOYEE_EUR = _CONSTANTS["OTHER_VORSORGE_CAP_EMPLOYEE_EUR"]
OTHER_VORSORGE_CAP_GENERAL_EUR = _CONSTANTS["OTHER_VORSORGE_CAP_GENERAL_EUR"]

# § 10c EStG Sonderausgaben-Pauschbetrag: €36 single / €72 joint.
# https://www.gesetze-im-internet.de/estg/__10c.html
SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR = _CONSTANTS["SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR"]
SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR = _CONSTANTS["SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR"]

# § 10 Abs. 3 Satz 1 EStG: the Höchstbetrag for retirement
# Vorsorgeaufwendungen equals the maximum (employer + employee) annual
# contribution to the knappschaftliche Rentenversicherung. The BMAS
# Sozialversicherungs-Rechengrößenverordnung 2025 abolished the West/Ost
# split — for 2025 there is a single bundeseinheitliche BBG of €118,800
# in the knappschaftliche RV, and the contribution rate is 24.7 %, so:
#   €118,800 × 0.247 = €29,343.60 → rounded by BMF to €29,344.
# The legacy "_RV_WEST_" suffix on the constant name is retained for
# fingerprint stability under invariants I1 / I2; the value is correct
# for the unified 2025 BBG.
# https://www.gesetze-im-internet.de/estg/__10.html
# https://www.bmas.de/DE/Service/Gesetze-und-Gesetzesvorhaben/sozialversicherungs-rechengroessen-2025.html
RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR = _CONSTANTS["RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR"]
RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR = _CONSTANTS["RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR"]
RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025 = _CONSTANTS["RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025"]

# § 10 Abs. 1 Nr. 3 Satz 4 EStG: statutory health insurance contributions
# entitled to Krankengeld must be reduced by 4 % to isolate the deductible
# basic-health portion. The default 4 % rate applies unless workspace facts
# show a different non-deductible share.
# https://www.gesetze-im-internet.de/estg/__10.html
STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE = _CONSTANTS["STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE"]


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def _require_unit_interval(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00") or value > D("1.00"):
        raise ValueError(f"{label} must be between 0 and 1 inclusive.")
    return value


def _allocate_total_by_weights(total: Decimal, weights: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    total = q2(total)
    if total == D("0.00") or not weights:
        return tuple(D("0.00") for _ in weights)
    total_weight = sum((max(weight, D("0.00")) for weight in weights), D("0.00"))
    if total_weight == D("0.00"):
        return tuple(D("0.00") for _ in weights)
    allocations: list[Decimal] = []
    remaining = total
    positive_indexes = [index for index, weight in enumerate(weights) if weight > D("0.00")]
    last_positive = positive_indexes[-1]
    for index, weight in enumerate(weights):
        if weight <= D("0.00"):
            allocations.append(D("0.00"))
            continue
        if index == last_positive:
            allocations.append(q2(remaining))
        else:
            share = q2(total * weight / total_weight)
            allocations.append(share)
            remaining -= share
    return tuple(allocations)


def retirement_special_expense_deduction_2025(
    employee_pension_contribution_eur: Decimal,
    employer_pension_contribution_eur: Decimal,
) -> Decimal:
    """§ 10 Abs. 1 Nr. 2 / Abs. 3 EStG single-person retirement Sonderausgaben.

    Authority: § 10 Abs. 1 Nr. 2 Satz 6 EStG, § 10 Abs. 3 Sätze 5-6 EStG.
    From 2023 onward the rate is 100 %, so the deductible amount for
    employees is effectively the employee share net of the cap.
    https://www.gesetze-im-internet.de/estg/__10.html
    """
    # Fix: do not double-count the tax-free employer pension share.
    # Under § 10 Abs. 1 Nr. 2 Satz 6 and Abs. 3 Sätze 5-6 EStG, the employer share is added
    # to the base and then subtracted again. From 2023 onward the rate is 100%, so the
    # deductible amount for employees is effectively the employee share.
    gross_retirement_base = min(
        employee_pension_contribution_eur + employer_pension_contribution_eur,
        RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR,
    )
    deductible_amount = gross_retirement_base - employer_pension_contribution_eur
    return q2(max(deductible_amount, D("0.00")))


def joint_retirement_special_expense_deductions_2025(
    people: tuple[object, ...],
    *,
    se_retirement_contributions: tuple[Decimal, ...] | None = None,
) -> tuple[Decimal, ...]:
    """§ 10 Abs. 3 Sätze 1, 2, 5, 6 EStG household retirement deductions.

    Doubles the cap for jointly assessed spouses (§ 10 Abs. 3 Satz 2 EStG),
    applies that cap to the combined retirement base, then subtracts all
    tax-free § 3 Nr. 62 employer shares. Per-spouse allocation is
    audit-output-only (the tax base uses the joint deduction).

    § 10 Abs. 1 Nr. 2 EStG: a self-employed spouse's own Altersvorsorge has
    no employer share, so it joins the combined base on the own-contribution
    side via ``se_retirement_contributions`` (per-person, aligned with
    ``people``; None = legitimately none). The § 10 Abs. 3 cap is applied
    exactly once over the combined base.
    https://www.gesetze-im-internet.de/estg/__10.html
    """
    # § 10 Abs. 3 Sätze 1, 2, 5 und 6 EStG doubles the cap for jointly assessed
    # spouses, applies that cap to the combined retirement base, then subtracts
    # all tax-free § 3 Nr. 62 employer shares. Per-spouse allocation is audit output only.
    #
    # § 10 Abs. 1 Nr. 2 EStG: a self-employed spouse's own Altersvorsorge
    # (Basisrente / RV / Versorgungswerk) is part of the SAME combined base the
    # § 10 Abs. 3 joint cap is applied to — there is no employer share for a
    # freelancer, so it adds to the employee (own-contribution) side and is
    # NOT subtracted again. ``se_retirement_contributions`` is per-person
    # aligned with ``people`` (None = legitimately none, treated as zeros);
    # passing it keeps the cap applied exactly once over the combined base.
    joint_cap = RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR * D("2")
    se_shares = (
        tuple(D("0.00") for _ in people)
        if se_retirement_contributions is None
        else se_retirement_contributions
    )
    if len(se_shares) != len(people):
        raise ValueError("se_retirement_contributions must match the people count.")
    employee_shares = tuple(
        _require_non_negative_decimal(
            person.wage.employee_pension_contribution_eur,
            label="employee_pension_contribution_eur",
        )
        + _require_non_negative_decimal(se, label="se_retirement_contributions_eur")
        for person, se in zip(people, se_shares, strict=True)
    )
    employer_shares = tuple(
        _require_non_negative_decimal(
            person.wage.employer_pension_contribution_eur,
            label="employer_pension_contribution_eur",
        )
        for person in people
    )
    gross_bases = tuple(
        employee + employer
        for employee, employer in zip(employee_shares, employer_shares, strict=True)
    )
    total_gross_base = sum(gross_bases, D("0.00"))
    if total_gross_base == D("0.00"):
        return tuple(D("0.00") for _ in people)
    capped_total_base = min(total_gross_base, joint_cap)
    household_deduction = q2(
        max(D("0.00"), capped_total_base - sum(employer_shares, D("0.00")))
    )
    return _allocate_total_by_weights(household_deduction, employee_shares)


def deductible_basic_health_contribution_2025(
    employee_health_insurance_eur: Decimal,
    employee_nursing_care_insurance_eur: Decimal,
    *,
    statutory_health_sick_pay_reduction_rate: Decimal,
) -> Decimal:
    """§ 10 Abs. 1 Nr. 3 Satz 4 EStG basic health + nursing Sonderausgabe.

    Reduces the statutory health-insurance contribution by 4 % (sick-pay
    component non-deductible) and adds nursing-care in full.
    https://www.gesetze-im-internet.de/estg/__10.html
    """
    # Fix: statutory health-insurance contributions with Krankengeld entitlement are not
    # fully deductible as basic health coverage. § 10 Abs. 1 Nr. 3 Satz 4 EStG requires
    # reducing the health-insurance portion by 4% for the sick-pay component unless facts
    # show a different non-deductible share.
    _require_non_negative_decimal(employee_health_insurance_eur, label="employee_health_insurance_eur")
    _require_non_negative_decimal(employee_nursing_care_insurance_eur, label="employee_nursing_care_insurance_eur")
    _require_unit_interval(
        statutory_health_sick_pay_reduction_rate,
        label="statutory_health_sick_pay_reduction_rate",
    )
    reduced_health = employee_health_insurance_eur * (D("1.00") - statutory_health_sick_pay_reduction_rate)
    return q2(max(reduced_health, D("0.00")) + employee_nursing_care_insurance_eur)


def other_vorsorge_allowed_employee_2025(
    health_and_nursing_contributions_eur: Decimal,
    other_vorsorge_contributions_eur: Decimal,
    *,
    cap_eur: Decimal = OTHER_VORSORGE_CAP_EMPLOYEE_EUR,
) -> Decimal:
    """§ 10 Abs. 4 Sätze 1-2 EStG single-person other-Vorsorge deduction.

    Authority: § 10 Abs. 4 Sätze 1-2 EStG. Basic health + nursing contributions
    consume the €1,900 (employee) or €2,800 (general) cap first; only unused
    room remains for § 10 Abs. 1 Nr. 3a contributions.
    https://www.gesetze-im-internet.de/estg/__10.html
    """
    # § 10 Abs. 4 Sätze 1-2 EStG uses either the 2,800 EUR general cap or the
    # 1,900 EUR employee/covered-health-cost cap. Basic health and nursing
    # contributions use that cap first; only unused room remains for § 10 Abs. 1 Nr. 3a.
    _require_non_negative_decimal(cap_eur, label="other_vorsorge_cap_eur")
    remaining_cap = cap_eur - min(
        health_and_nursing_contributions_eur,
        cap_eur,
    )
    return q2(max(D("0.00"), min(other_vorsorge_contributions_eur, remaining_cap)))


def joint_other_vorsorge_allowed_employee_2025(
    health_and_nursing_contributions: tuple[Decimal, ...],
    other_vorsorge_contributions: tuple[Decimal, ...],
    other_vorsorge_caps: tuple[Decimal, ...] | None = None,
) -> tuple[Decimal, ...]:
    """§ 10 Abs. 4 Sätze 1-4 EStG joint other-Vorsorge deduction.

    Per-spouse cap is summed to a joint cap; basic health + nursing consume
    the joint cap first, the remainder limits other-Vorsorge.
    """
    # § 10 Abs. 4 Sätze 1-4 EStG determines each spouse's 1,900/2,800 EUR cap first,
    # then uses the sum as the joint cap. Basic health/nursing contributions consume
    # the common cap before unemployment-insurance or other § 10 Abs. 1 Nr. 3a amounts.
    caps = other_vorsorge_caps or tuple(
        OTHER_VORSORGE_CAP_EMPLOYEE_EUR for _ in health_and_nursing_contributions
    )
    if len(caps) != len(health_and_nursing_contributions):
        raise ValueError("other_vorsorge_caps must match the people count.")
    joint_cap = q2(sum((_require_non_negative_decimal(cap, label="other_vorsorge_cap_eur") for cap in caps), D("0.00")))
    total_health_and_nursing = q2(sum(health_and_nursing_contributions, D("0.00")))
    total_other = q2(sum(other_vorsorge_contributions, D("0.00")))
    remaining_cap = joint_cap - min(total_health_and_nursing, joint_cap)
    total_allowed = q2(max(D("0.00"), min(total_other, remaining_cap)))
    if total_allowed == D("0.00") or total_other == D("0.00"):
        return tuple(D("0.00") for _ in other_vorsorge_contributions)
    return _allocate_total_by_weights(total_allowed, other_vorsorge_contributions)
