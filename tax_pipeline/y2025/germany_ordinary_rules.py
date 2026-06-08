"""Per-stage rule functions for the Germany 2025 ordinary-income graph.

This module is the single execution path for the twelve declared
``DE25-00`` through ``DE25-10`` LawStages. Bodies are lifted from the
historical ``compute_joint_ordinary_assessment_2025`` monolith in
``tax_pipeline/y2025/germany_law.py``, split on stage boundaries so every
legal value tracked by ``JointOrdinaryAssessment2025`` is produced by a
``LawRule.calculate`` invocation through ``execute_rule_graph``.

Filing posture is an input fact, not a rule-list branch. The three
posture-aware stages (DE25-00, DE25-07, DE25-08) read
``de.ordinary.filing_posture`` from the facts dict and branch internally;
every taxpayer runs the same 12 declared stages in the same order.

Authority:

- § 2 EStG (https://www.gesetze-im-internet.de/estg/__2.html) - income
  computation order.
- § 9, § 9a EStG (https://www.gesetze-im-internet.de/estg/__9.html /
  __9a.html) - Werbungskosten / Arbeitnehmer-Pauschbetrag.
- § 10, § 10c EStG (https://www.gesetze-im-internet.de/estg/__10.html)
  - Sonderausgaben including the lump-sum Pauschbetrag.
- § 19 EStG - employment income.
- § 22 Nr. 3 EStG - other income (with statutory threshold).
- § 26, § 26a, § 26b EStG - filing posture / spousal assessment.
- § 32a Abs. 1, 5 EStG - basic and splitting tariffs (BMF
  Programmablaufplan 2025 carries the dated rounding rules).
- § 36 Abs. 2, 3 EStG - withholding-credit ordering.
- SolzG 1995 § 3, § 4 - solidarity surcharge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import LawRule, LawStage, RuleGraphExecution, execute_rule_graph
from tax_pipeline.y2025.germany_law import (
    SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR,
    SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR,
    SPENDENABZUG_2025_GDE_FRACTION_CAP,
    TARIFF_2025_GROUND_ALLOWANCE_EUR,
    WORKER_ALLOWANCE_PER_PERSON_EUR,
    GermanyChildrenFacts2025,
    JointOrdinaryAssessment2025,
    JointOrdinaryInputs2025,
    PersonOrdinaryAssessment2025,
    _allocations_or_default,
    _normalized_germany_filing_posture_2025,
    _require_non_negative_decimal,
    _validate_joint_ordinary_inputs_2025,
    altersentlastungsbetrag_2025,
    arbeitszimmer_deductible_2025,
    aussergewoehnliche_belastungen_deductible_2025,
    behinderung_pauschbetrag_2025,
    ceil_euro,
    deductible_basic_health_contribution_2025,
    german_income_tax_single_2025,
    german_income_tax_split_2025,
    german_soli_assessment_2025,
    home_office_tagespauschale_2025,
    joint_other_vorsorge_allowed_employee_2025,
    joint_retirement_special_expense_deductions_2025,
    other_income_22nr3_taxable_2025,
    other_vorsorge_allowed_employee_2025,
    q2,
    retirement_special_expense_deduction_2025,
    spendenabzug_2025,
    unterhaltsleistungen_deductible_2025,
)
from tax_pipeline.y2025.germany_stages import (
    germany_ordinary_law_stages_2025,
)
from tax_pipeline.pipeline_context import set_pipeline_context_value

ZERO_EUR = Decimal("0.00")
GERMANY_ORDINARY_EXECUTION_CONTEXT_KEY = "de25.ordinary_rule_graph_execution"
"""Pipeline-context key under which ``execute_germany_ordinary_rule_graph``
stashes the executed ``RuleGraphExecution`` for in-memory hand-off to the
narrative packet builder.
"""


def de25_00_filing_posture_gate(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 26 / § 26a / § 26b EStG: validate filing-posture eligibility (joint
    # election prerequisites for married_joint, per-spouse allocations for
    # married_separate, single-person assessment for single) before any
    # household-level aggregation or tariff selection.
    raw_inputs = facts["de.ordinary.raw_inputs"]
    if not isinstance(raw_inputs, JointOrdinaryInputs2025):
        raise TypeError("de.ordinary.raw_inputs must be a JointOrdinaryInputs2025 instance")
    posture = _normalized_germany_filing_posture_2025(raw_inputs)
    _validate_joint_ordinary_inputs_2025(raw_inputs)
    return {"de.ordinary.filing_posture": posture}


def de25_01_wage_income(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 19 Abs. 1 EStG: employment income before any work-expense reduction.
    people = facts["de.ordinary.people"]
    by_person = tuple(q2(p.wage.gross_wage_eur) for p in people)
    return {
        "de.ordinary.gross_wages": {
            "total_eur": q2(sum(by_person, ZERO_EUR)),
            "by_person": by_person,
        }
    }


def de25_02_werbungskosten(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 9 EStG actual Werbungskosten vs. § 9a EStG Arbeitnehmer-Pauschbetrag,
    # max-of (capped at gross wage). Per-person breakdown retained for
    # Anlage N rendering.
    people = facts["de.ordinary.people"]
    worker_allowance: Decimal = Decimal(str(facts["de.constants.worker_allowance_per_person"]))
    by_person = []
    for person in people:
        # § 9 Abs. 5 + § 4 Abs. 5 Satz 1 Nr. 6c EStG: explicit manual work-equipment
        # positions feed the same § 9 work-expense bucket as invoice-derived items.
        work_equipment = q2(
            sum((item.deductible_amount_eur for item in person.work_equipment_items), ZERO_EUR)
            + person.manual_work_equipment_deduction_eur
        )
        home_office_deduction = home_office_tagespauschale_2025(
            person.home_office_days_without_visit,
            person.home_office_days_with_visit,
            visit_days_no_other_workplace=person.home_office_visit_days_no_other_workplace,
        )
        actual_werbungskosten = q2(
            work_equipment
            + home_office_deduction
            + person.telecom_deduction_eur
            + person.employment_legal_insurance_deduction_eur
            + person.cross_border_tax_help_deduction_eur
        )
        allowed_werbungskosten = max(
            actual_werbungskosten,
            min(worker_allowance, person.wage.gross_wage_eur),
        )
        by_person.append({
            "work_equipment_eur": work_equipment,
            "home_office_deduction_eur": home_office_deduction,
            "telecom_deduction_eur": q2(person.telecom_deduction_eur),
            "employment_legal_insurance_deduction_eur": q2(person.employment_legal_insurance_deduction_eur),
            "cross_border_tax_help_deduction_eur": q2(person.cross_border_tax_help_deduction_eur),
            "actual_werbungskosten_eur": actual_werbungskosten,
            "allowed_werbungskosten_eur": allowed_werbungskosten,
        })
    return {
        "de.ordinary.work_expenses": {
            "total_allowed_eur": q2(sum((p["allowed_werbungskosten_eur"] for p in by_person), ZERO_EUR)),
            "by_person": tuple(by_person),
        }
    }


def de25_03_net_employment(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 2 Abs. 2 Satz 1 Nr. 2 EStG: net employment income = gross wage minus
    # § 9/§ 9a Werbungskosten. Per-person breakdown summed at the end.
    gross_wages = facts["de.ordinary.gross_wages"]
    work_expenses = facts["de.ordinary.work_expenses"]
    by_person_gross = gross_wages["by_person"]
    by_person_we = work_expenses["by_person"]
    by_person = tuple(
        q2(g - we["allowed_werbungskosten_eur"]) for g, we in zip(by_person_gross, by_person_we, strict=True)
    )
    return {
        "de.ordinary.net_employment_income": {
            "total_eur": q2(sum(by_person, ZERO_EUR)),
            "by_person": by_person,
        }
    }


def de25_04_other_22nr3(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 22 Nr. 3 EStG: per-person taxable other income after the statutory
    # threshold; married_joint requires explicit per-spouse allocations that
    # reconcile to the aggregate, otherwise the aggregate is allocated to
    # one person.
    posture: str = facts["de.ordinary.filing_posture"]
    aggregate: Decimal = Decimal(str(facts["de.ordinary.other_income_22nr3"]))
    threshold: Decimal = Decimal(str(facts["de.ordinary.other_income_22nr3_threshold"]))
    by_person_explicit = facts.get("de.ordinary.other_income_22nr3_by_person", ())
    people_count = len(facts["de.ordinary.people"])

    if posture == "married_joint":
        if by_person_explicit:
            if len(by_person_explicit) != people_count:
                raise ValueError("other_income_22nr3 allocations must match the people count.")
            if q2(sum(by_person_explicit, ZERO_EUR)) != q2(aggregate):
                raise ValueError("per-spouse § 22 Nr. 3 allocations must reconcile to the aggregate amount.")
            allocations = tuple(
                other_income_22nr3_taxable_2025(amount, threshold) for amount in by_person_explicit
            )
        else:
            if aggregate != ZERO_EUR:
                raise ValueError(
                    "Germany married_joint requires per-spouse § 22 Nr. 3 allocations for nonzero amounts."
                )
            allocations = tuple(ZERO_EUR for _ in range(people_count))
    else:
        raw_allocations = _allocations_or_default(
            tuple(by_person_explicit),
            people_count=people_count,
            aggregate_amount=aggregate,
            filing_posture=posture,
            label="other_income_22nr3",
        )
        allocations = tuple(
            other_income_22nr3_taxable_2025(amount, threshold) for amount in raw_allocations
        )
    return {
        "de.ordinary.other_income_22nr3_taxable": {
            "total_eur": q2(sum(allocations, ZERO_EUR)),
            "by_person": tuple(q2(a) for a in allocations),
            "aggregate_input_eur": q2(aggregate),
        }
    }


def de25_altersentlastungsbetrag(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 24a EStG Altersentlastungsbetrag — sliding cohort allowance for
    # taxpayers who turned 64 BEFORE the start of the assessment year.
    # § 24a Satz 2 Nr. 1 EStG excludes § 19 wages (Versorgungsbezüge are
    # similarly excluded under Nr. 2). Net employment income is post-
    # Werbungskosten employment income — including it in the eligible
    # base would re-introduce § 19 amounts the statute carves out, so
    # only § 22 Nr. 3 amounts feed the rate × base computation. The age
    # threshold is checked per person; per-person results are summed for
    # the household total (married couples each carry their own cohort).
    posture: str = facts["de.ordinary.filing_posture"]
    del posture  # filing posture does not change § 24a; allowance is per-person
    people = facts["de.ordinary.people"]
    other_income = facts["de.ordinary.other_income_22nr3_taxable"]
    tax_year = int(facts["de.constants.altersentlastungsbetrag_tax_year"])
    by_person_amounts: list[Decimal] = []
    by_person_eligible_base: list[Decimal] = []
    for person, other_eur in zip(people, other_income["by_person"], strict=True):
        eligible_base = q2(_require_non_negative_decimal(other_eur, label="altersentlastungsbetrag_eligible_base_eur"))
        amount = altersentlastungsbetrag_2025(
            birth_year=person.birth_year,
            eligible_income_eur=eligible_base,
            tax_year=tax_year,
        )
        by_person_amounts.append(amount)
        by_person_eligible_base.append(eligible_base)
    return {
        "de.ordinary.altersentlastungsbetrag": {
            "total_eur": q2(sum(by_person_amounts, ZERO_EUR)),
            "by_person": tuple(by_person_amounts),
            "by_person_eligible_base_eur": tuple(by_person_eligible_base),
            "by_person_birth_year": tuple(int(p.birth_year) for p in people),
            "tax_year": tax_year,
        }
    }


def de25_arbeitszimmer(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer (Jahrespauschale or
    # actual costs). § 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG mutual-
    # exclusion: ``tagespauschale_days_total`` aggregates per-person
    # home-office days already counted under § 4 Abs. 5 Satz 1 Nr. 6c
    # (DE25-02 Werbungskosten); a non-zero total forbids the Nr. 6b
    # election for the same period.
    raw_inputs: JointOrdinaryInputs2025 = facts["de.ordinary.raw_inputs"]
    people = facts["de.ordinary.people"]
    tagespauschale_days_total = sum(
        int(person.home_office_days_without_visit) + int(person.home_office_days_with_visit)
        for person in people
    )
    deductible = arbeitszimmer_deductible_2025(
        arbeitszimmer_claimed=raw_inputs.arbeitszimmer_claimed,
        qualifies_as_mittelpunkt=raw_inputs.arbeitszimmer_qualifies_as_mittelpunkt,
        actual_costs_eur=raw_inputs.arbeitszimmer_actual_costs_eur,
        tagespauschale_days_total=tagespauschale_days_total,
    )
    return {
        "de.ordinary.arbeitszimmer": {
            "deductible_eur": q2(deductible),
            "claimed": bool(raw_inputs.arbeitszimmer_claimed),
            "qualifies_as_mittelpunkt": bool(raw_inputs.arbeitszimmer_qualifies_as_mittelpunkt),
            "actual_costs_eur": q2(raw_inputs.arbeitszimmer_actual_costs_eur),
            "tagespauschale_days_total": tagespauschale_days_total,
        }
    }


def de25_05_retirement_sa(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 10 Abs. 1 Nr. 2, § 10 Abs. 3, § 3 Nr. 62 EStG: retirement
    # Vorsorgeaufwendungen with employer-share subtraction; married_joint
    # applies the spousal cap aggregator.
    posture: str = facts["de.ordinary.filing_posture"]
    people = facts["de.ordinary.people"]
    per_person_retirement = tuple(
        retirement_special_expense_deduction_2025(
            person.wage.employee_pension_contribution_eur,
            person.wage.employer_pension_contribution_eur,
        )
        for person in people
    )
    if posture == "married_joint":
        per_person_retirement = joint_retirement_special_expense_deductions_2025(people)
    retirement_total = q2(sum(per_person_retirement, ZERO_EUR))
    # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
    # ``de.ordinary.retirement_special_expenses_total_eur`` is the
    # § 10 Abs. 1 Nr. 2 / Abs. 3 EStG scalar total that lands on
    # Anlage Vorsorgeaufwand Zeilen 4-9 (Beiträge zur gesetzlichen
    # Rentenversicherung / berufsständischen Versorgungswerken).
    # Promoting it to a sibling top-level scalar output (alongside the
    # existing per-person dict) lets the renderer read a fingerprinted
    # Decimal directly via the I11 LegalValue envelope.
    # https://www.gesetze-im-internet.de/estg/__10.html
    return {
        "de.ordinary.retirement_special_expenses": {
            "total_eur": retirement_total,
            "by_person": tuple(q2(r) for r in per_person_retirement),
        },
        "de.ordinary.retirement_special_expenses_total_eur": retirement_total,
    }


def de25_06_health_vorsorge_sa(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 10 Abs. 1 Nr. 3 + Nr. 3a + § 10 Abs. 4 EStG: deductible health/nursing
    # contributions plus other Vorsorge subject to posture cap.
    posture: str = facts["de.ordinary.filing_posture"]
    people = facts["de.ordinary.people"]
    per_person_health = tuple(
        deductible_basic_health_contribution_2025(
            person.wage.employee_health_insurance_eur,
            person.wage.employee_nursing_care_insurance_eur,
            statutory_health_sick_pay_reduction_rate=person.health_insurance_sick_pay_reduction_rate,
        )
        for person in people
    )
    per_person_other_contributions = tuple(
        person.wage.employee_unemployment_insurance_eur for person in people
    )
    per_person_other_allowed = tuple(
        other_vorsorge_allowed_employee_2025(
            health,
            other,
            cap_eur=person.other_vorsorge_cap_eur,
        )
        for person, health, other in zip(people, per_person_health, per_person_other_contributions, strict=True)
    )
    if posture == "married_joint":
        per_person_other_allowed = joint_other_vorsorge_allowed_employee_2025(
            per_person_health,
            tuple(q2(c) for c in per_person_other_contributions),
            tuple(person.other_vorsorge_cap_eur for person in people),
        )
    by_person_health_vorsorge = tuple(
        q2(h + o) for h, o in zip(per_person_health, per_person_other_allowed, strict=True)
    )
    total_health_vorsorge = q2(sum(by_person_health_vorsorge, ZERO_EUR))
    # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket scalars
    # for Anlage Vorsorgeaufwand:
    #   - basic_health = sum(per_person_health) = § 10 Abs. 1 Nr. 3 EStG
    #     (Krankenversicherung + Pflegeversicherung), Anlage
    #     Vorsorgeaufwand Zeilen 11-14.
    #   - other_allowed = sum(per_person_other_allowed) = § 10 Abs. 1
    #     Nr. 3a EStG (sonstige Vorsorgeaufwendungen), Anlage
    #     Vorsorgeaufwand Zeilen 31 ff. (within § 10 Abs. 4 cap).
    # Promoting these to declared scalar outputs lets the renderer read
    # fingerprinted Decimals directly via the I11 LegalValue envelope
    # rather than re-deriving them from the existing dict's per-person
    # breakdown (a projection-side sum that would re-introduce a pragma
    # bypass otherwise).
    # https://www.gesetze-im-internet.de/estg/__10.html
    basic_health_total = q2(sum(per_person_health, ZERO_EUR))
    other_allowed_total = q2(sum(per_person_other_allowed, ZERO_EUR))
    return {
        "de.ordinary.health_vorsorge_special_expenses": {
            "total_eur": total_health_vorsorge,
            "by_person": by_person_health_vorsorge,
            "by_person_health_and_nursing": tuple(q2(h) for h in per_person_health),
            "by_person_other_vorsorge_contributions": tuple(q2(o) for o in per_person_other_contributions),
            "by_person_other_vorsorge_allowed": tuple(q2(o) for o in per_person_other_allowed),
        },
        "de.ordinary.health_vorsorge_total_eur": total_health_vorsorge,
        "de.ordinary.health_vorsorge_basic_health_eur": basic_health_total,
        "de.ordinary.health_vorsorge_other_allowed_eur": other_allowed_total,
    }


def de25_06b_sonderausgaben_pauschbetrag(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 10 + § 10c EStG: total Sonderausgaben including the statutory minimum
    # Pauschbetrag (joint amount when filing married_joint, per-person single
    # amount otherwise, as added inside the legacy posture branches).
    posture: str = facts["de.ordinary.filing_posture"]
    retirement = facts["de.ordinary.retirement_special_expenses"]
    health_vorsorge = facts["de.ordinary.health_vorsorge_special_expenses"]
    pauschbetrag_joint: Decimal = Decimal(str(facts["de.constants.sonderausgaben_pauschbetrag_joint"]))
    pauschbetrag_single: Decimal = Decimal(str(facts["de.constants.sonderausgaben_pauschbetrag_single"]))
    by_person_retirement = retirement["by_person"]
    by_person_health = health_vorsorge["by_person"]
    by_person_no_pauschbetrag = tuple(
        q2(r + h) for r, h in zip(by_person_retirement, by_person_health, strict=True)
    )
    if posture == "married_joint":
        total = q2(sum(by_person_no_pauschbetrag, ZERO_EUR) + pauschbetrag_joint)
        pauschbetrag_applied = pauschbetrag_joint
    else:
        total = q2(
            sum(by_person_no_pauschbetrag, ZERO_EUR) + pauschbetrag_single * len(by_person_no_pauschbetrag)
        )
        pauschbetrag_applied = pauschbetrag_single * len(by_person_no_pauschbetrag)
    return {
        "de.ordinary.total_special_expenses": {
            "total_eur": total,
            "by_person_no_pauschbetrag": by_person_no_pauschbetrag,
            "pauschbetrag_applied_eur": pauschbetrag_applied,
        },
        # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar promoted to a
        # sibling output for the I11 LegalValue envelope (Anlage
        # Sonderausgaben renderer's § 10c statutory-minimum row).
        # https://www.gesetze-im-internet.de/estg/__10c.html
        "de.ordinary.sonderausgaben_pauschbetrag_applied_eur": q2(pauschbetrag_applied),
    }


def de25_spendenabzug(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 10b Abs. 1 Satz 1 Nr. 1 EStG: Spendenabzug capped at 20 % of GdE.
    # GdE = sum_employment + § 22 Nr. 3 income − § 24a Altersentlastungs-
    # betrag (§ 2 Abs. 4 EStG ordering).
    raw_inputs: JointOrdinaryInputs2025 = facts["de.ordinary.raw_inputs"]
    net_employment = facts["de.ordinary.net_employment_income"]
    other_income = facts["de.ordinary.other_income_22nr3_taxable"]
    altersentlastung = facts["de.ordinary.altersentlastungsbetrag"]
    gde = q2(
        net_employment["total_eur"]
        + other_income["total_eur"]
        - altersentlastung["total_eur"]
    )
    deductible = spendenabzug_2025(
        donations_eur=raw_inputs.charitable_donations_eur,
        gesamtbetrag_der_einkuenfte_eur=max(gde, ZERO_EUR),
        carryforward_eur=raw_inputs.charitable_donations_carryforward_eur,
    )
    deductible_q2 = q2(deductible)
    return {
        "de.ordinary.spendenabzug": {
            "deductible_eur": deductible_q2,
            "donations_eur": q2(raw_inputs.charitable_donations_eur),
            "gesamtbetrag_der_einkuenfte_eur": gde,
            "cap_eur": q2(max(gde, ZERO_EUR) * SPENDENABZUG_2025_GDE_FRACTION_CAP),
        },
        # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar promoted to a
        # sibling output so the Anlage Sonderausgaben renderer can read
        # a fingerprinted Decimal directly via the I11 LegalValue
        # envelope (instead of digging into the dict-typed sibling
        # under a renderer-side projection).
        # https://www.gesetze-im-internet.de/estg/__10b.html
        "de.ordinary.spendenabzug_deductible_eur": deductible_q2,
    }


def de25_aussergewoehnliche_belastungen(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 33 EStG außergewöhnliche Belastungen, after § 33 Abs. 3 EStG
    # zumutbare Belastung (slab progression per BFH VI R 75/14). The GdE
    # base is sum(net_employment) + other_income_22nr3_taxable − § 24a
    # Altersentlastungsbetrag (§ 2 Abs. 4 EStG ordering).
    raw_inputs: JointOrdinaryInputs2025 = facts["de.ordinary.raw_inputs"]
    net_employment = facts["de.ordinary.net_employment_income"]
    other_income = facts["de.ordinary.other_income_22nr3_taxable"]
    altersentlastung = facts["de.ordinary.altersentlastungsbetrag"]
    medical_expenses = q2(_require_non_negative_decimal(
        raw_inputs.medical_expenses_eur, label="medical_expenses_eur"
    ))
    family_category = raw_inputs.zumutbare_belastung_family_category
    gde = q2(
        net_employment["total_eur"]
        + other_income["total_eur"]
        - altersentlastung["total_eur"]
    )
    deductible, burden = aussergewoehnliche_belastungen_deductible_2025(
        medical_expenses_eur=medical_expenses,
        gesamtbetrag_der_einkuenfte_eur=max(gde, ZERO_EUR),
        family_category=family_category,
    )
    return {
        "de.ordinary.aussergewoehnliche_belastungen": {
            "deductible_eur": deductible,
            "zumutbare_belastung_eur": burden,
            "medical_expenses_eur": medical_expenses,
            "gesamtbetrag_der_einkuenfte_eur": gde,
            "family_category": family_category,
        }
    }


def de25_unterhaltsleistungen(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 33a Abs. 1 EStG Unterhaltsleistungen — capped by the
    # Grundfreibetrag minus Eigenbezüge of the recipient above the
    # statutory €624 Freibetrag.
    raw_inputs: JointOrdinaryInputs2025 = facts["de.ordinary.raw_inputs"]
    grundfreibetrag = Decimal(str(facts["de.constants.unterhaltsleistungen_grundfreibetrag"]))
    deductible = unterhaltsleistungen_deductible_2025(
        support_payments_eur=raw_inputs.support_payments_eur,
        recipient_income_eur=raw_inputs.support_recipient_income_eur,
        relationship=raw_inputs.support_recipient_relationship,
        grundfreibetrag_eur=grundfreibetrag,
    )
    deductible_q2 = q2(deductible)
    return {
        "de.ordinary.unterhaltsleistungen": {
            "deductible_eur": deductible_q2,
            "support_payments_eur": q2(raw_inputs.support_payments_eur),
            "recipient_income_eur": q2(raw_inputs.support_recipient_income_eur),
            "relationship": raw_inputs.support_recipient_relationship or "",
            "grundfreibetrag_eur": q2(grundfreibetrag),
        },
        # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar promoted to a
        # sibling output for the I11 LegalValue envelope (Anlage
        # Sonderausgaben renderer / Anlage Unterhalt — § 33a Abs. 1
        # is functionally außergewöhnliche Belastungen in besonderen
        # Fällen, but the engine surfaces it under the Sonderausgaben
        # block per the form-mapping plan).
        # https://www.gesetze-im-internet.de/estg/__33a.html
        "de.ordinary.unterhaltsleistungen_deductible_eur": deductible_q2,
    }


def de25_behinderung_pauschbetrag(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 33b Abs. 3 EStG flat allowance by GdB tier or hilflos/blind
    # status. Each spouse carries their own GdB; the household total is
    # the sum.
    #
    # Gap 2 — § 33b Abs. 5 EStG transferral: when the parents claim a
    # qualifying child's Pauschbetrag (profile election validated at
    # Pipeline 1 boundary), the per-child §-33b-Abs.-3-EStG amount is
    # added to the household total. The Pipeline 1 derivation
    # ``DERIVE-DE25-CHILDREN`` produces the aggregate at
    # ``de.derived.children_disability_pauschbetrag_total_eur``; reading
    # it here is what lets the transferral flow naturally through DE25-07
    # zvE → DE25-08 tariff at the parents' marginal rate, exactly as
    # § 33b Abs. 5 Satz 2 EStG intends.
    #
    # § 33b Abs. 5 Satz 3 EStG governs the per-spouse split:
    #     "Der einem Kind zustehende Pauschbetrag … wird auf die
    #      Elternteile zu gleichen Teilen aufgeteilt, es sei denn, sie
    #      beantragen gemeinsam eine andere Aufteilung."
    # Statutory default is 50/50 between the two parents; the joint
    # election in Anlage Kind 2025 Zeile 66 captures any other ratio. We
    # implement the default + override here. For single-parent
    # households the split collapses to (1.0,); for married_joint the
    # split is bookkeeping only because § 26b EStG joint assessment
    # uses one zvE.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    people = facts["de.ordinary.people"]
    children_transferred_total = q2(
        Decimal(
            str(facts["de.derived.children_disability_pauschbetrag_total_eur"])
        )
    )
    raw_split = facts["de.profile.disability_pauschbetrag_transfer_split"]
    by_person: list[Decimal] = []
    by_person_gdb: list[int] = []
    by_person_hilflos: list[bool] = []
    for person in people:
        amount = behinderung_pauschbetrag_2025(
            gdb=int(person.gdb),
            hilflos_or_blind=bool(person.hilflos_or_blind),
        )
        by_person.append(q2(amount))
        by_person_gdb.append(int(person.gdb))
        by_person_hilflos.append(bool(person.hilflos_or_blind))
    parents_only_total = q2(sum(by_person, ZERO_EUR))
    n_people = len(by_person)

    # Resolve the per-person allocation shares for the §-33b-Abs.-5
    # transferral. § 33b Abs. 5 Satz 3 EStG defaults to "zu gleichen
    # Teilen"; the joint-election clause permits another ratio. Anlage
    # Kind 2025 only models two parents — Zeile 66 carries the
    # percentage-split override; ≥3 person slots is not a posture the
    # statute contemplates.
    if children_transferred_total > ZERO_EUR and n_people > 0:
        if raw_split is None:
            # Default to even shares for any number of slots; the
            # 50/50 case is the §-33b-Abs.-5-Satz-3 statutory default
            # for two parents and the only legally-defined posture for
            # the household.
            shares = tuple(Decimal("1") / Decimal(n_people) for _ in range(n_people))
        else:
            shares = _validate_disability_pauschbetrag_split_2025(
                raw_split, n_people=n_people
            )
        # Apply the share to the household transferral total. Quantize
        # each share's contribution at q2 and reconcile the last entry
        # to absorb any cent-level rounding so the per-person sum equals
        # the household total exactly.
        share_amounts: list[Decimal] = []
        running = ZERO_EUR
        for index, share in enumerate(shares):
            if index == n_people - 1:
                allocation = q2(children_transferred_total - running)
            else:
                allocation = q2(children_transferred_total * share)
                running = q2(running + allocation)
            share_amounts.append(allocation)
        for index in range(n_people):
            by_person[index] = q2(by_person[index] + share_amounts[index])
    household_total = q2(parents_only_total + children_transferred_total)
    return {
        "de.ordinary.behinderung_pauschbetrag": {
            "total_eur": household_total,
            "parents_only_total_eur": parents_only_total,
            "child_transferred_eur": children_transferred_total,
            "by_person": tuple(by_person),
            "by_person_gdb": tuple(by_person_gdb),
            "by_person_hilflos_or_blind": tuple(by_person_hilflos),
        }
    }


def _validate_disability_pauschbetrag_split_2025(
    raw: Any,
    *,
    n_people: int,
) -> tuple[Decimal, ...]:
    """Validate a § 33b Abs. 5 Satz 3 EStG joint-election split override.

    The statute requires the parents to "gemeinsam eine andere Aufteilung
    beantragen"; an invalid declaration cannot silently revert to 50/50
    because the engine would otherwise mask a defective profile. We
    therefore fail closed on:

    - non-iterable / wrong-length declarations,
    - any negative share (Anlage Kind 2025 Zeile 66 percentages must be
      non-negative),
    - shares that do not sum to exactly 1 (within ``q2`` cent precision).

    Authority: § 33b Abs. 5 Satz 3 EStG
    (https://www.gesetze-im-internet.de/estg/__33b.html). Anlage Kind
    2025 Zeile 66 captures the override; an empty Zeile 66 means the
    statutory default applies and Pipeline 1 surfaces ``None`` here.
    """
    try:
        entries = tuple(raw)
    except TypeError as exc:
        raise ValueError(
            "elections.germany_disability_pauschbetrag_transfer_split must be "
            "an iterable of Decimal shares per § 33b Abs. 5 Satz 3 EStG "
            "(joint-election clause); got "
            f"{type(raw).__name__}. "
            "https://www.gesetze-im-internet.de/estg/__33b.html"
        ) from exc
    if len(entries) != n_people:
        raise ValueError(
            "elections.germany_disability_pauschbetrag_transfer_split must "
            f"have exactly {n_people} share(s) (one per assessed person) "
            "per § 33b Abs. 5 Satz 3 EStG; got "
            f"{len(entries)} entries. "
            "https://www.gesetze-im-internet.de/estg/__33b.html"
        )
    shares: list[Decimal] = []
    for entry in entries:
        try:
            share = Decimal(str(entry))
        except Exception as exc:
            raise ValueError(
                "elections.germany_disability_pauschbetrag_transfer_split "
                "share entries must be Decimal-convertible per § 33b Abs. 5 "
                f"Satz 3 EStG; got {entry!r}. "
                "https://www.gesetze-im-internet.de/estg/__33b.html"
            ) from exc
        if share < Decimal("0"):
            raise ValueError(
                "elections.germany_disability_pauschbetrag_transfer_split "
                "shares must be non-negative per § 33b Abs. 5 Satz 3 EStG "
                f"(Anlage Kind 2025 Zeile 66 percentage); got {share}. "
                "https://www.gesetze-im-internet.de/estg/__33b.html"
            )
        shares.append(share)
    total_share = sum(shares, Decimal("0"))
    if q2(total_share) != q2(Decimal("1")):
        raise ValueError(
            "elections.germany_disability_pauschbetrag_transfer_split shares "
            f"must sum to 1.00 per § 33b Abs. 5 Satz 3 EStG; got {total_share}. "
            "https://www.gesetze-im-internet.de/estg/__33b.html"
        )
    return tuple(shares)


def de25_07_taxable_income(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 2 Abs. 4 / Abs. 5 EStG taxable-income assembly. § 24a EStG
    # Altersentlastungsbetrag and § 33 EStG außergewöhnliche Belastungen
    # reduce the Gesamtbetrag der Einkünfte / Einkommen on the way to zvE.
    posture: str = facts["de.ordinary.filing_posture"]
    net_employment = facts["de.ordinary.net_employment_income"]
    other_income = facts["de.ordinary.other_income_22nr3_taxable"]
    altersentlastungsbetrag = facts["de.ordinary.altersentlastungsbetrag"]
    arbeitszimmer = facts["de.ordinary.arbeitszimmer"]
    spendenabzug = facts["de.ordinary.spendenabzug"]
    aussergewoehnliche = facts["de.ordinary.aussergewoehnliche_belastungen"]
    unterhaltsleistungen = facts["de.ordinary.unterhaltsleistungen"]
    behinderung = facts["de.ordinary.behinderung_pauschbetrag"]
    total_special = facts["de.ordinary.total_special_expenses"]
    pauschbetrag_single: Decimal = Decimal(str(facts["de.constants.sonderausgaben_pauschbetrag_single"]))
    aussergewoehnliche_eur = q2(aussergewoehnliche["deductible_eur"])
    unterhalt_eur = q2(unterhaltsleistungen["deductible_eur"])
    spendenabzug_eur = q2(spendenabzug["deductible_eur"])
    arbeitszimmer_eur = q2(arbeitszimmer["deductible_eur"])
    if posture == "married_joint":
        joint_taxable_income = q2(
            net_employment["total_eur"]
            + other_income["total_eur"]
            - altersentlastungsbetrag["total_eur"]
            - arbeitszimmer_eur
            - total_special["total_eur"]
            - spendenabzug_eur
            - aussergewoehnliche_eur
            - unterhalt_eur
            - behinderung["total_eur"]
        )
        return {
            "de.ordinary.taxable_income": {
                "joint_taxable_income_eur": joint_taxable_income,
                "by_person": (joint_taxable_income,),  # joint household has one taxable base
            }
        }
    else:
        by_person_taxable: list[Decimal] = []
        n_people = len(net_employment["by_person"])
        # Joint deductions (medical, support, donations, Arbeitszimmer)
        # are allocated to the first person in married_separate trace
        # contexts; single-person filers see the full amount. § 33b is
        # per-person and follows person.gdb.
        joint_extras = [ZERO_EUR] * n_people
        if n_people:
            joint_extras[0] = q2(
                spendenabzug_eur
                + aussergewoehnliche_eur
                + unterhalt_eur
                + arbeitszimmer_eur
            )
        for net_p, other_p, age_relief_p, no_pausch_p, joint_extra, behind_p in zip(
            net_employment["by_person"],
            other_income["by_person"],
            altersentlastungsbetrag["by_person"],
            total_special["by_person_no_pauschbetrag"],
            joint_extras,
            behinderung["by_person"],
            strict=True,
        ):
            person_special_expenses = q2(no_pausch_p + pauschbetrag_single)
            person_taxable = q2(
                net_p + other_p - age_relief_p - person_special_expenses - joint_extra - behind_p
            )
            by_person_taxable.append(person_taxable)
        joint_taxable_income = q2(sum(by_person_taxable, ZERO_EUR))
        return {
            "de.ordinary.taxable_income": {
                "joint_taxable_income_eur": joint_taxable_income,
                "by_person": tuple(by_person_taxable),
            }
        }


def de25_08_income_tax_tariff(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 32a Abs. 1 / Abs. 5 EStG (BMF Programmablaufplan 2025): married_joint
    # applies splitting tariff per § 26b/§ 32a(5); otherwise per-person
    # § 32a(1) basic tariff is summed for the household trace.
    posture: str = facts["de.ordinary.filing_posture"]
    taxable_income = facts["de.ordinary.taxable_income"]
    if posture == "married_joint":
        joint_income_tax = german_income_tax_split_2025(taxable_income["joint_taxable_income_eur"])
        return {
            "de.ordinary.income_tax": {
                "joint_income_tax_eur": q2(joint_income_tax),
                "by_person": (q2(joint_income_tax),),
            }
        }
    else:
        by_person_tax = tuple(
            german_income_tax_single_2025(zve) for zve in taxable_income["by_person"]
        )
        return {
            "de.ordinary.income_tax": {
                "joint_income_tax_eur": q2(sum(by_person_tax, ZERO_EUR)),
                "by_person": tuple(q2(t) for t in by_person_tax),
            }
        }


def de25_09_ordinary_soli(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # SolzG 1995 § 3, § 4: solidarity surcharge on assessed income tax. Married_joint
    # uses the joint amount; single/married_separate sums per-person soli.
    posture: str = facts["de.ordinary.filing_posture"]
    income_tax = facts["de.ordinary.income_tax"]
    if posture == "married_joint":
        joint_soli = german_soli_assessment_2025(
            income_tax["joint_income_tax_eur"], filing_posture="married_joint"
        )
        return {
            "de.ordinary.solidarity_surcharge": {
                "joint_solidarity_surcharge_eur": q2(joint_soli),
                "by_person": (q2(joint_soli),),
            }
        }
    else:
        by_person_soli = tuple(
            german_soli_assessment_2025(t, filing_posture="single") for t in income_tax["by_person"]
        )
        return {
            "de.ordinary.solidarity_surcharge": {
                "joint_solidarity_surcharge_eur": q2(sum(by_person_soli, ZERO_EUR)),
                "by_person": tuple(q2(s) for s in by_person_soli),
            }
        }


def de25_10_ordinary_credits(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 36 Abs. 2, 3 EStG: withholding-credit ordering (per-credit-type ceiling
    # to full euros) plus prepayments, applied against assessed tax + soli.
    posture: str = facts["de.ordinary.filing_posture"]
    people = facts["de.ordinary.people"]
    income_tax = facts["de.ordinary.income_tax"]
    soli = facts["de.ordinary.solidarity_surcharge"]
    prepayments_total: Decimal = Decimal(str(facts["de.ordinary.prepayments"]))
    prepayments_by_person = facts.get("de.ordinary.prepayments_by_person", ())

    withheld_wage_tax = q2(
        ceil_euro(
            sum(
                (
                    _require_non_negative_decimal(
                        person.wage.withheld_wage_tax_eur,
                        label="withheld_wage_tax_eur",
                    )
                    for person in people
                ),
                ZERO_EUR,
            )
        )
    )
    withheld_wage_soli = q2(
        ceil_euro(
            sum(
                (
                    _require_non_negative_decimal(
                        person.wage.withheld_solidarity_surcharge_eur,
                        label="withheld_solidarity_surcharge_eur",
                    )
                    for person in people
                ),
                ZERO_EUR,
            )
        )
    )

    if posture == "married_joint":
        ordinary_refund = q2(
            withheld_wage_tax
            + withheld_wage_soli
            + prepayments_total
            - income_tax["joint_income_tax_eur"]
            - soli["joint_solidarity_surcharge_eur"]
        )
    else:
        prepayment_allocations = _allocations_or_default(
            tuple(prepayments_by_person),
            people_count=len(people),
            aggregate_amount=prepayments_total,
            filing_posture=posture,
            label="prepayments",
        )
        per_person_refund = []
        for person, person_tax, person_soli, prepayment in zip(
            people,
            income_tax["by_person"],
            soli["by_person"],
            prepayment_allocations,
            strict=True,
        ):
            person_refund = q2(
                ceil_euro(_require_non_negative_decimal(person.wage.withheld_wage_tax_eur, label="withheld_wage_tax_eur"))
                + ceil_euro(_require_non_negative_decimal(person.wage.withheld_solidarity_surcharge_eur, label="withheld_solidarity_surcharge_eur"))
                + prepayment
                - person_tax
                - person_soli
            )
            per_person_refund.append(person_refund)
        ordinary_refund = q2(sum(per_person_refund, ZERO_EUR))

    return {
        "de.ordinary.refund_before_capital": {
            "refund_or_balance_eur": ordinary_refund,
            "withheld_wage_tax_eur": withheld_wage_tax,
            "withheld_solidarity_surcharge_eur": withheld_wage_soli,
            "prepayments_eur": q2(prepayments_total),
        }
    }


# Wave 11A: ``de25_children_credits`` and ``germany_children_law_rules_2025``
# moved to ``tax_pipeline.y2025.germany_children_rules`` when the children
# sub-graph was promoted to a sibling Pipeline 2 graph. Importers should
# use that module directly.


_RULE_FUNCTIONS = {
    "DE25-00-FILING-POSTURE-GATE": de25_00_filing_posture_gate,
    "DE25-01-WAGE-INCOME": de25_01_wage_income,
    "DE25-02-WERBUNGSKOSTEN": de25_02_werbungskosten,
    "DE25-03-NET-EMPLOYMENT": de25_03_net_employment,
    "DE25-04-OTHER-22NR3": de25_04_other_22nr3,
    "DE25-ALTERSENTLASTUNGSBETRAG": de25_altersentlastungsbetrag,
    "DE25-ARBEITSZIMMER": de25_arbeitszimmer,
    "DE25-05-RETIREMENT-SA": de25_05_retirement_sa,
    "DE25-06-HEALTH-VORSORGE-SA": de25_06_health_vorsorge_sa,
    "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG": de25_06b_sonderausgaben_pauschbetrag,
    "DE25-SPENDENABZUG": de25_spendenabzug,
    "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN": de25_aussergewoehnliche_belastungen,
    "DE25-UNTERHALTSLEISTUNGEN": de25_unterhaltsleistungen,
    "DE25-BEHINDERUNG-PAUSCHBETRAG": de25_behinderung_pauschbetrag,
    "DE25-07-TAXABLE-INCOME": de25_07_taxable_income,
    "DE25-08-INCOME-TAX-TARIFF": de25_08_income_tax_tariff,
    "DE25-09-ORDINARY-SOLI": de25_09_ordinary_soli,
    "DE25-10-ORDINARY-CREDITS": de25_10_ordinary_credits,
}


def germany_ordinary_law_rules_2025() -> tuple[LawRule, ...]:
    stages = germany_ordinary_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(f"No germany ordinary calculate function registered for {stage.stage_id}")
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def germany_ordinary_initial_facts_2025(
    inputs: JointOrdinaryInputs2025,
    *,
    children_disability_pauschbetrag_total_eur: Decimal = Decimal("0.00"),
    disability_pauschbetrag_transfer_split: tuple[Decimal, ...] | None = None,
) -> dict[str, Any]:
    """Assemble the ordinary-graph initial facts.

    Gap 2 — § 33b Abs. 5 EStG transferral: callers must pass the
    Pipeline 1 derived total
    ``de.derived.children_disability_pauschbetrag_total_eur`` so the
    ordinary stage ``DE25-BEHINDERUNG-PAUSCHBETRAG`` can add it to the
    parents' household total. The default ``Decimal("0.00")`` keeps
    legacy test fixtures (no children declared, no transferral) working
    without explicit thread-through; production callers
    (``germany_model.py``) pass the live derivation output.

    Gap 2 deferred — § 33b Abs. 5 Satz 3 EStG split override:
    ``disability_pauschbetrag_transfer_split=None`` selects the
    statutory 50/50 default ("zu gleichen Teilen aufgeteilt"); a tuple
    of Decimal shares summing to 1 carries the joint-election override
    captured on Anlage Kind 2025 Zeile 66.

    Authority for the new fields: § 33b Abs. 5 EStG and § 33b Abs. 5
    Satz 3 EStG (https://www.gesetze-im-internet.de/estg/__33b.html).
    """
    return {
        "de.ordinary.raw_inputs": inputs,
        "de.profile.filing_posture": inputs.filing_posture or "",
        "de.profile.joint_assessment_prerequisites": {
            "joint_assessment_prerequisites_validated": inputs.joint_assessment_prerequisites_validated,
        },
        "de.profile.separate_assessment_allocations": {
            "other_income_22nr3_by_person_eur": inputs.other_income_22nr3_by_person_eur,
            "prepayments_by_person_eur": inputs.prepayments_by_person_eur,
        },
        "de.ordinary.people": inputs.people,
        "de.ordinary.other_income_22nr3": inputs.other_income_22nr3_eur,
        "de.ordinary.other_income_22nr3_threshold": inputs.other_income_22nr3_threshold_eur,
        "de.ordinary.other_income_22nr3_by_person": inputs.other_income_22nr3_by_person_eur,
        "de.ordinary.prepayments": inputs.prepayments_eur,
        "de.ordinary.prepayments_by_person": inputs.prepayments_by_person_eur,
        # Gap 2 — § 33b Abs. 5 EStG transferral total. Pipeline 1
        # derivation aggregate consumed by DE25-BEHINDERUNG-PAUSCHBETRAG.
        "de.derived.children_disability_pauschbetrag_total_eur": (
            children_disability_pauschbetrag_total_eur
        ),
        # § 33b Abs. 5 Satz 3 EStG joint-election override. ``None``
        # selects the statutory 50/50 default; a Decimal tuple summing
        # to 1 carries the parents' explicit allocation per Anlage
        # Kind 2025 Zeile 66.
        # https://www.gesetze-im-internet.de/estg/__33b.html
        "de.profile.disability_pauschbetrag_transfer_split": (
            disability_pauschbetrag_transfer_split
        ),
        "de.constants.worker_allowance_per_person": WORKER_ALLOWANCE_PER_PERSON_EUR,
        "de.constants.sonderausgaben_pauschbetrag_joint": SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR,
        "de.constants.sonderausgaben_pauschbetrag_single": SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR,
        # § 24a EStG cohort table is keyed by the assessment year so the
        # rule can resolve "year_turned_64 < tax_year" correctly. Pinned
        # to 2025 because the tariff-table snapshot in this module is the
        # 2025 BMF Programmablaufplan; rolling forward to a later tax
        # year requires a new law-module snapshot.
        "de.constants.altersentlastungsbetrag_tax_year": 2025,
        # § 33a Abs. 1 Satz 1 EStG ties the cap to the Grundfreibetrag,
        # which equals TARIFF_2025_GROUND_ALLOWANCE_EUR for 2025.
        # https://www.gesetze-im-internet.de/estg/__33a.html
        "de.constants.unterhaltsleistungen_grundfreibetrag": TARIFF_2025_GROUND_ALLOWANCE_EUR,
    }


def germany_ordinary_initial_fingerprints_2025(initial_facts: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_germany_ordinary_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        germany_ordinary_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(GERMANY_ORDINARY_EXECUTION_CONTEXT_KEY, execution)
    return execution


def germany_ordinary_assessment_from_final_facts(
    final_facts: Mapping[str, Any],
    *,
    inputs: JointOrdinaryInputs2025,
) -> JointOrdinaryAssessment2025:
    """Project executed final_facts back into the legacy view dataclass.

    Per Phase 3 of the engine restructure, ``JointOrdinaryAssessment2025`` is a
    typed view assembled from rule-graph outputs.
    """
    posture: str = final_facts["de.ordinary.filing_posture"]
    work_expenses = final_facts["de.ordinary.work_expenses"]
    net_employment = final_facts["de.ordinary.net_employment_income"]
    other_income = final_facts["de.ordinary.other_income_22nr3_taxable"]
    retirement = final_facts["de.ordinary.retirement_special_expenses"]
    health_vorsorge = final_facts["de.ordinary.health_vorsorge_special_expenses"]
    # C3-prereq (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar
    # § 10 Abs. 1 Nr. 3 + Nr. 3a + Abs. 4 EStG total promoted to a
    # declared DE25-06-HEALTH-VORSORGE-SA output for I11 fingerprinting
    # at the form-line boundary.
    health_vorsorge_total_eur: Decimal = final_facts[
        "de.ordinary.health_vorsorge_total_eur"
    ]
    # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket scalars
    # for Anlage Vorsorgeaufwand line decomposition.
    health_vorsorge_basic_health_eur: Decimal = final_facts[
        "de.ordinary.health_vorsorge_basic_health_eur"
    ]
    health_vorsorge_other_allowed_eur: Decimal = final_facts[
        "de.ordinary.health_vorsorge_other_allowed_eur"
    ]
    retirement_special_expenses_total_eur: Decimal = final_facts[
        "de.ordinary.retirement_special_expenses_total_eur"
    ]
    # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket scalars
    # for Anlage Sonderausgaben line decomposition.
    spendenabzug_deductible_eur: Decimal = final_facts[
        "de.ordinary.spendenabzug_deductible_eur"
    ]
    unterhaltsleistungen_deductible_eur: Decimal = final_facts[
        "de.ordinary.unterhaltsleistungen_deductible_eur"
    ]
    sonderausgaben_pauschbetrag_applied_eur: Decimal = final_facts[
        "de.ordinary.sonderausgaben_pauschbetrag_applied_eur"
    ]
    total_special = final_facts["de.ordinary.total_special_expenses"]
    taxable_income = final_facts["de.ordinary.taxable_income"]
    income_tax = final_facts["de.ordinary.income_tax"]
    soli = final_facts["de.ordinary.solidarity_surcharge"]
    refund = final_facts["de.ordinary.refund_before_capital"]

    person_results: list[PersonOrdinaryAssessment2025] = []
    for person, we, net_eur, retirement_eur, health_eur, other_contrib_eur, other_allowed_eur in zip(
        inputs.people,
        work_expenses["by_person"],
        net_employment["by_person"],
        retirement["by_person"],
        health_vorsorge["by_person_health_and_nursing"],
        health_vorsorge["by_person_other_vorsorge_contributions"],
        health_vorsorge["by_person_other_vorsorge_allowed"],
        strict=True,
    ):
        person_results.append(
            PersonOrdinaryAssessment2025(
                slot=person.slot,
                order_label=person.order_label,
                display_name=person.display_name,
                owner=person.owner,
                wage=person.wage,
                work_equipment_items=person.work_equipment_items,
                manual_work_equipment_deduction_eur=q2(person.manual_work_equipment_deduction_eur),
                work_equipment_eur=we["work_equipment_eur"],
                home_office_days_without_visit=person.home_office_days_without_visit,
                home_office_days_with_visit=person.home_office_days_with_visit,
                home_office_deduction_eur=we["home_office_deduction_eur"],
                telecom_deduction_eur=we["telecom_deduction_eur"],
                employment_legal_insurance_deduction_eur=we["employment_legal_insurance_deduction_eur"],
                cross_border_tax_help_deduction_eur=we["cross_border_tax_help_deduction_eur"],
                actual_werbungskosten_eur=we["actual_werbungskosten_eur"],
                allowed_werbungskosten_eur=we["allowed_werbungskosten_eur"],
                income_after_werbungskosten_eur=net_eur,
                retirement_contributions_eur=retirement_eur,
                health_and_nursing_contributions_eur=health_eur,
                other_vorsorge_contributions_eur=other_contrib_eur,
                other_vorsorge_allowed_eur=other_allowed_eur,
                total_special_expenses_eur=q2(retirement_eur + health_eur + other_allowed_eur),
            )
        )

    return JointOrdinaryAssessment2025(
        filing_posture=posture,
        people=tuple(person_results),
        other_income_22nr3_eur=q2(other_income["aggregate_input_eur"]),
        other_income_22nr3_taxable_eur=q2(other_income["total_eur"]),
        other_income_22nr3_by_person_taxable_eur=other_income["by_person"],
        sum_income_after_werbungskosten_eur=q2(net_employment["total_eur"]),
        retirement_contributions_eur=q2(retirement["total_eur"]),
        health_and_nursing_contributions_eur=q2(
            sum(health_vorsorge["by_person_health_and_nursing"], ZERO_EUR)
        ),
        other_vorsorge_contributions_eur=q2(
            sum(health_vorsorge["by_person_other_vorsorge_contributions"], ZERO_EUR)
        ),
        other_vorsorge_allowed_eur=q2(
            sum(health_vorsorge["by_person_other_vorsorge_allowed"], ZERO_EUR)
        ),
        health_vorsorge_total_eur=q2(health_vorsorge_total_eur),
        health_vorsorge_basic_health_eur=q2(health_vorsorge_basic_health_eur),
        health_vorsorge_other_allowed_eur=q2(health_vorsorge_other_allowed_eur),
        retirement_special_expenses_total_eur=q2(retirement_special_expenses_total_eur),
        spendenabzug_deductible_eur=q2(spendenabzug_deductible_eur),
        unterhaltsleistungen_deductible_eur=q2(unterhaltsleistungen_deductible_eur),
        sonderausgaben_pauschbetrag_applied_eur=q2(sonderausgaben_pauschbetrag_applied_eur),
        total_special_expenses_eur=q2(total_special["total_eur"]),
        joint_taxable_income_eur=q2(taxable_income["joint_taxable_income_eur"]),
        joint_income_tax_eur=q2(income_tax["joint_income_tax_eur"]),
        joint_solidarity_surcharge_eur=q2(soli["joint_solidarity_surcharge_eur"]),
        withheld_wage_tax_eur=q2(refund["withheld_wage_tax_eur"]),
        withheld_wage_solidarity_surcharge_eur=q2(refund["withheld_solidarity_surcharge_eur"]),
        prepayments_eur=q2(refund["prepayments_eur"]),
        ordinary_refund_before_capital_eur=q2(refund["refund_or_balance_eur"]),
    )


__all__ = [
    "GERMANY_ORDINARY_EXECUTION_CONTEXT_KEY",
    "execute_germany_ordinary_rule_graph",
    "germany_ordinary_assessment_from_final_facts",
    "germany_ordinary_initial_facts_2025",
    "germany_ordinary_initial_fingerprints_2025",
    "germany_ordinary_law_rules_2025",
    "de25_00_filing_posture_gate",
    "de25_01_wage_income",
    "de25_02_werbungskosten",
    "de25_03_net_employment",
    "de25_04_other_22nr3",
    "de25_altersentlastungsbetrag",
    "de25_arbeitszimmer",
    "de25_05_retirement_sa",
    "de25_06_health_vorsorge_sa",
    "de25_06b_sonderausgaben_pauschbetrag",
    "de25_spendenabzug",
    "de25_aussergewoehnliche_belastungen",
    "de25_unterhaltsleistungen",
    "de25_behinderung_pauschbetrag",
    "de25_07_taxable_income",
    "de25_08_income_tax_tariff",
    "de25_09_ordinary_soli",
    "de25_10_ordinary_credits",
]
