from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from tax_pipeline.analysis_inputs import structured_input_files
from tax_pipeline.y2025.germany_law import (
    Child2025,
    GermanyChildrenFacts2025,
    JointOrdinaryInputs2025,
    OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR,
    OTHER_VORSORGE_CAP_EMPLOYEE_EUR,
    OTHER_VORSORGE_CAP_GENERAL_EUR,
    PersonOrdinaryInputs2025,
    STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE,
    WageFacts2025,
    WorkEquipmentItem2025,
    aggregate_germany_children_facts_2025,
    assert_germany_csv_statutory_constants_2025,
)
from tax_pipeline.paths import YearPaths

D = Decimal
WORK_EQUIPMENT_GWG_IMMEDIATE_EXPENSE_LIMIT_EUR = D("800.00")


def _read_row_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: (value or "") for key, value in row.items() if key is not None} for row in csv.DictReader(handle)]


def _optional_row_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return _read_row_csv(path)


def _parse_optional_bool(value: str, *, label: str) -> bool | None:
    cleaned = str(value).strip().lower()
    if cleaned == "":
        return None
    if cleaned in {"true", "1", "yes", "y", "ja"}:
        return True
    if cleaned in {"false", "0", "no", "n", "nein"}:
        return False
    raise ValueError(f"{label} must be true, false, or blank.")


def _required_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean.")
    return value


def _people_rows_by_id(paths: YearPaths) -> dict[str, dict[str, str]]:
    if not paths.people_path.exists():
        return {}
    return {row.get("person_id", ""): row for row in _read_row_csv(paths.people_path)}


def _decimal_map(path: Path) -> dict[str, Decimal]:
    return {row["key"]: D(row["value"]) for row in _read_row_csv(path)}


def _profile(paths: YearPaths) -> dict:
    return json.loads(paths.profile_path.read_text(encoding="utf-8"))


# § 51a EStG attaches Kirchensteuer (church tax) at 8 % or 9 % of the assessed
# Einkommensteuer for taxpayers belonging to a recognized Religionsgemeinschaft.
# The 2025 model does not yet implement Kirchensteuer, so it must fail closed
# if a taxpayer asserts membership.
# https://www.gesetze-im-internet.de/estg/__51a.html
KIRCHENSTEUER_NONE_VALUES = {"none", "no", "keine", "nicht_mitglied"}


def _required_germany_kirchensteuer_membership(profile: dict) -> str:
    elections = profile.get("elections")
    if not isinstance(elections, dict):
        raise ValueError(
            "Missing required elections block in profile.json (must declare "
            "germany_kirchensteuer_membership per § 51a EStG)."
        )
    raw = elections.get("germany_kirchensteuer_membership")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            "Missing required elections.germany_kirchensteuer_membership in "
            "profile.json (§ 51a EStG): set to 'none' if not a member of a "
            "Kirchensteuer-collecting Religionsgemeinschaft, otherwise specify "
            "membership (e.g. 'EVK', 'RKK', 'FREIKIRCHE')."
        )
    membership = raw.strip().lower()
    if membership not in KIRCHENSTEUER_NONE_VALUES:
        raise NotImplementedError(
            f"Germany Kirchensteuer (§ 51a EStG) is not modeled for 2025. "
            f"Profile elections.germany_kirchensteuer_membership={membership!r} "
            "asserts membership in a Kirchensteuer-collecting Religionsgemeinschaft; "
            "the engine refuses to compute a return that would silently omit the "
            "8 % or 9 % church-tax surcharge."
        )
    return membership


def _manual_overrides(paths: YearPaths) -> dict:
    return json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))


def _required_person_config(person_rows: dict, key: str, *, slot: str) -> object:
    # Fix: material deduction inputs must be explicit in year config so they are auditable
    # facts/positions, not silent zero defaults.
    if key not in person_rows:
        raise ValueError(f"Missing deductions.persons.{slot}.{key} in manual_overrides.json.")
    return person_rows[key]


def load_german_person_slots(paths: YearPaths) -> list[dict]:
    profile = _profile(paths)
    german_return = profile.get("german_return")
    if not isinstance(german_return, dict):
        raise ValueError("Missing german_return config in profile.json.")
    person_slots = german_return.get("person_slots")
    if not isinstance(person_slots, list) or not person_slots:
        raise ValueError("Missing or empty german_return.person_slots config in profile.json.")
    for index, slot in enumerate(person_slots):
        if not isinstance(slot, dict):
            raise ValueError(f"german_return.person_slots[{index}] must be an object.")
        if not str(slot.get("slot", "")).strip():
            raise ValueError(f"german_return.person_slots[{index}].slot must be provided.")
        if not str(slot.get("order_label", "")).strip():
            raise ValueError(f"german_return.person_slots[{index}].order_label must be provided.")
    return person_slots


def _validate_married_joint_profile(profile: dict, person_slots: list[dict]) -> None:
    german_return = profile.get("german_return", {})
    prerequisites = german_return.get("joint_assessment_prerequisites")
    if not isinstance(prerequisites, dict):
        raise ValueError(
            "Germany married_joint requires german_return.joint_assessment_prerequisites in profile.json."
        )
    required_true = [
        "married_or_registered_partners",
        "not_permanently_separated",
        "unrestricted_tax_liability",
    ]
    missing_or_false = [key for key in required_true if prerequisites.get(key) is not True]
    if missing_or_false:
        raise ValueError(
            "Germany married_joint requires true joint_assessment_prerequisites: "
            + ", ".join(missing_or_false)
        )
    if prerequisites.get("joint_election") is False:
        raise ValueError("Germany married_joint cannot use joint_election=false.")
    household = profile.get("household", {})
    marital_status = str(household.get("marital_status_on_dec_31", "")).strip().lower()
    if marital_status not in {"married", "registered_partner", "life_partner", "civil_partnership"}:
        if prerequisites.get("eligibility_existed_at_start_or_arose_during_year") is not True:
            # § 26 Abs. 1 EStG allows eligibility if the spouse conditions existed at the start
            # of the year or arose during the year; § 2 Abs. 8 EStG applies spouse rules to life partners.
            raise ValueError(
                "Germany married_joint requires married/registered-partner status or explicit in-year § 26 eligibility."
            )
    owners = [slot.get("owner") for slot in person_slots]
    if any(not isinstance(owner, str) or not owner.strip() for owner in owners) or len(set(owners)) != len(owners):
        raise ValueError("Germany married_joint requires each person slot to have a distinct non-empty owner.")


def _fact_documents(paths: YearPaths, doc_type: str, owner: str | None) -> list[dict]:
    matches: list[dict] = []
    for path in sorted(paths.facts_root.glob("*.facts.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("doc_type") != doc_type:
            continue
        if payload.get("owner") != owner:
            continue
        matches.append(payload)
    if not matches:
        raise FileNotFoundError(f"Missing {doc_type} facts for owner={owner!r}")
    return matches


def _required_fact(payload: dict, key: str) -> Decimal:
    matches = [fact for fact in payload["facts"] if fact["key"] == key]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one fact {key} in {payload['relative_path']}")
    return D(str(matches[0]["value"]))


def _load_wage_totals(paths: YearPaths, owner: str | None) -> WageFacts2025:
    payloads = _fact_documents(paths, "german_lohnsteuer_pdf", owner)
    totals: dict[str, Decimal] = {
        "gross_wage_eur": D("0"),
        "withheld_wage_tax_eur": D("0"),
        "withheld_solidarity_surcharge_eur": D("0"),
        "multiannual_wage_eur": D("0"),
        "employer_pension_contribution_eur": D("0"),
        "employee_pension_contribution_eur": D("0"),
        "employee_health_insurance_eur": D("0"),
        "employee_nursing_care_insurance_eur": D("0"),
        "employee_unemployment_insurance_eur": D("0"),
    }
    for payload in payloads:
        for key in totals:
            totals[key] += _required_fact(payload, key)
    return WageFacts2025(
        owner=owner,
        source_files=tuple(sorted(payload["relative_path"] for payload in payloads)),
        **totals,
    )


def _sum_document_fact(paths: YearPaths, doc_type: str, key: str) -> Decimal:
    total = D("0.00")
    for payload in _fact_documents(paths, doc_type, owner=None):
        total += _required_fact(payload, key)
    return total


def _germany_filing_posture(paths: YearPaths, person_slots: list[dict]) -> str:
    profile = _profile(paths)
    jurisdictions = profile.get("jurisdictions", {})
    germany = jurisdictions.get("germany", {})
    posture = str(germany.get("filing_posture", "")).strip().lower()
    if posture:
        if posture == "married_joint":
            _validate_married_joint_profile(profile, person_slots)
        return posture
    if len(person_slots) == 1:
        return "single"
    raise ValueError("Germany two-person returns require an explicit jurisdictions.germany.filing_posture.")


def _person_manual_deductions(paths: YearPaths, slot: str, wage: WageFacts2025 | None = None) -> dict[str, object]:
    deductions = _manual_overrides(paths).get("deductions", {})
    persons = deductions.get("persons", {})
    person_rows = persons.get(slot)
    if not isinstance(person_rows, dict):
        raise ValueError(f"Missing deductions.persons.{slot} config in manual_overrides.json.")
    if "home_office_days" in deductions:
        # Fix: reject the legacy top-level home-office fallback so the year config has one
        # explicit source of truth per person.
        raise ValueError("Legacy deductions.home_office_days fallback is no longer supported.")
    days_without_visit = int(
        _required_person_config(
            person_rows,
            "home_office_days_without_first_workplace_visit",
            slot=slot,
        )
    )
    if days_without_visit < 0:
        raise ValueError(f"{slot}.home_office_days_without_first_workplace_visit must be non-negative.")
    days_with_visit = int(
        _required_person_config(
            person_rows,
            "home_office_days_with_first_workplace_visit",
            slot=slot,
        )
    )
    if days_with_visit < 0:
        raise ValueError(f"{slot}.home_office_days_with_first_workplace_visit must be non-negative.")
    visit_days_no_other_workplace = _required_bool(
        person_rows.get("home_office_first_workplace_visit_days_have_no_other_workplace", False),
        label=f"{slot}.home_office_first_workplace_visit_days_have_no_other_workplace",
    )
    if days_with_visit and not visit_days_no_other_workplace:
        raise ValueError(
            f"{slot}.home_office_days_with_first_workplace_visit requires "
            "home_office_first_workplace_visit_days_have_no_other_workplace=true."
        )
    sick_pay_rate = D(
        str(
            _required_person_config(
                person_rows,
                "health_insurance_sick_pay_reduction_rate",
                slot=slot,
            )
        )
    )
    if sick_pay_rate < D("0.00") or sick_pay_rate > D("1.00"):
        raise ValueError(f"{slot}.health_insurance_sick_pay_reduction_rate must be between 0 and 1 inclusive.")
    people_row = _people_rows_by_id(paths).get(slot, {})
    sick_pay_fact = _parse_optional_bool(
        people_row.get("german_statutory_health_with_sick_pay", ""),
        label=f"people.csv {slot}.german_statutory_health_with_sick_pay",
    )
    if sick_pay_fact is True and sick_pay_rate != STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE:
        # § 10 Abs. 1 Nr. 3 Satz 4 EStG requires the statutory 4% reduction when the
        # health-insurance contribution can give rise to Krankengeld or a substitute benefit.
        raise ValueError(
            f"{slot}.health_insurance_sick_pay_reduction_rate must be 0.04 under § 10 Abs. 1 Nr. 3 Satz 4 EStG."
        )
    if sick_pay_fact is False and sick_pay_rate != D("0.00"):
        raise ValueError(
            f"{slot}.health_insurance_sick_pay_reduction_rate must be 0.00 when people.csv says there is no Krankengeld entitlement."
        )
    if (
        sick_pay_fact is None
        and wage is not None
        and (wage.employee_health_insurance_eur > D("0.00") or wage.employee_nursing_care_insurance_eur > D("0.00"))
    ):
        raise ValueError(
            f"people.csv {slot}.german_statutory_health_with_sick_pay must be true or false when health contributions are present."
        )
    cap_raw = str(people_row.get("german_other_vorsorge_cap_eur", "")).strip()
    if not cap_raw:
        # § 10 Abs. 4 EStG chooses a person-specific 1,900 EUR or 2,800 EUR cap.
        # The loader must not silently assume employee status when this fact is missing.
        raise ValueError(
            f"people.csv {slot}.german_other_vorsorge_cap_eur must be explicit under § 10 Abs. 4 EStG."
        )
    other_vorsorge_cap = D(cap_raw)
    if other_vorsorge_cap not in {OTHER_VORSORGE_CAP_EMPLOYEE_EUR, OTHER_VORSORGE_CAP_GENERAL_EUR}:
        raise ValueError(
            f"people.csv {slot}.german_other_vorsorge_cap_eur must be 1900.00 or 2800.00 under § 10 Abs. 4 EStG."
        )
    work_equipment_items = _required_person_config(person_rows, "work_equipment_items", slot=slot)
    if not isinstance(work_equipment_items, list):
        raise ValueError(f"deductions.persons.{slot}.work_equipment_items must be a list.")
    return {
        "home_office_days_without_first_workplace_visit": days_without_visit,
        "home_office_days_with_first_workplace_visit": days_with_visit,
        "home_office_first_workplace_visit_days_have_no_other_workplace": visit_days_no_other_workplace,
        # Allow software-alignment shortcuts like a partner's 110 EUR work equipment amount to live
        # as explicit manual § 9 positions instead of pretending they came from invoice facts.
        "manual_work_equipment_deduction_eur": D(
            str(_required_person_config(person_rows, "manual_work_equipment_deduction_eur", slot=slot))
        ),
        "telecom_deduction_eur": D(
            str(_required_person_config(person_rows, "telecom_deduction_eur", slot=slot))
        ),
        "cross_border_tax_help_deduction_eur": D(
            str(_required_person_config(person_rows, "cross_border_tax_help_deduction_eur", slot=slot))
        ),
        "employment_legal_insurance_deduction_eur": D(
            str(
                _required_person_config(
                    person_rows,
                    "employment_legal_insurance_deduction_eur",
                    slot=slot,
                )
            )
        ),
        "health_insurance_sick_pay_reduction_rate": sick_pay_rate,
        "other_vorsorge_cap_eur": other_vorsorge_cap,
        "work_equipment_items": tuple(
            str(item).strip()
            for item in work_equipment_items
            if str(item).strip()
        ),
    }


def _load_work_equipment_items_by_person(
    paths: YearPaths,
    person_slots: list[dict],
) -> dict[str, tuple[WorkEquipmentItem2025, ...]]:
    manual_overrides = _manual_overrides(paths)
    work_use_percentages = manual_overrides.get("deductions", {}).get("work_use_percentages", {})
    if not isinstance(work_use_percentages, dict):
        raise ValueError("manual_overrides.json deductions.work_use_percentages must be an object.")
    person_item_map = {
        slot["slot"]: set(_person_manual_deductions(paths, slot["slot"])["work_equipment_items"])
        for slot in person_slots
    }
    equipment_path = paths.facts_root / "de-equipment-source-facts.csv"
    equipment_rows = _optional_row_csv(equipment_path)
    if not equipment_rows:
        # Fix: years without claimed equipment should not fail before the legal-threshold checks
        # run. Only require the facts file when config says equipment is actually being claimed.
        configured_items = set().union(*person_item_map.values()) if person_item_map else set()
        configured_work_shares = {
            key for key, value in work_use_percentages.items() if D(str(value)) != D("0")
        }
        if configured_items or configured_work_shares:
            raise FileNotFoundError(
                "Missing de-equipment-source-facts.csv while equipment deductions are configured."
            )
        return {slot["slot"]: tuple() for slot in person_slots}

    equipment_amount_keys = {
        row["key"].removesuffix("_amount_eur")
        for row in equipment_rows
        if row["key"].endswith("_amount_eur")
    }
    equipment_values = {row["key"]: D(row["value"]) for row in equipment_rows}
    configured_items = set().union(*person_item_map.values()) if person_item_map else set()
    missing_share_items = sorted(configured_items - set(work_use_percentages))
    if missing_share_items:
        raise ValueError(
            "Missing work-use percentages for configured equipment items in manual_overrides.json: "
            + ", ".join(missing_share_items)
        )
    extra_share_items = sorted(
        key
        for key, value in work_use_percentages.items()
        if D(str(value)) != D("0") and key not in equipment_amount_keys
    )
    if extra_share_items:
        raise ValueError(
            "Configured work-use percentages without matching equipment source facts: "
            + ", ".join(extra_share_items)
        )

    assigned_items: dict[str, str] = {}
    items_by_person: dict[str, list[WorkEquipmentItem2025]] = {slot["slot"]: [] for slot in person_slots}
    for row in equipment_rows:
        amount_key = row["key"]
        if not amount_key.endswith("_amount_eur"):
            continue
        base_key = amount_key.removesuffix("_amount_eur")
        if base_key not in work_use_percentages:
            if any(base_key in configured_items for configured_items in person_item_map.values()):
                raise ValueError(
                    f"Missing work-use percentage for configured equipment item {base_key!r} in manual_overrides.json."
                )
            continue
        share = D(str(work_use_percentages[base_key]))
        if share < D("0.00") or share > D("1.00"):
            raise ValueError(
                f"Work-use percentage for equipment item {base_key!r} must be between 0 and 1 inclusive."
            )
        if share == D("0"):
            continue

        owners = [slot for slot, configured_items in person_item_map.items() if base_key in configured_items]
        # Fix: force explicit per-person equipment attribution in config so the law layer no longer
        # hard-assigns all household equipment to person_1.
        if not owners:
            raise ValueError(
                f"Equipment item {base_key!r} has a work-use share but is not assigned to any person in config/manual_overrides.json."
            )
        if len(owners) > 1:
            raise ValueError(
                f"Equipment item {base_key!r} is assigned to multiple people in config/manual_overrides.json."
            )
        owner_slot = owners[0]
        if base_key in assigned_items:
            raise ValueError(f"Equipment item {base_key!r} was assigned twice.")
        assigned_items[base_key] = owner_slot
        gross_amount = D(row["value"])
        current_year_key = f"{base_key}_current_year_deductible_eur"
        if gross_amount > WORK_EQUIPMENT_GWG_IMMEDIATE_EXPENSE_LIMIT_EUR and current_year_key not in equipment_values:
            # § 9 Abs. 1 Nr. 6-7 EStG points durable work equipment into AfA treatment.
            # § 6 Abs. 2 EStG allows immediate expensing only inside the GWG shortcut, so
            # high-value items need a source-fact current-year deductible amount.
            raise ValueError(
                f"Equipment item {base_key!r} exceeds the GWG shortcut and requires a current-year deductible amount."
            )
        current_year_amount = equipment_values.get(current_year_key, gross_amount)
        items_by_person[owner_slot].append(
            WorkEquipmentItem2025(
                key=base_key,
                gross_amount_eur=gross_amount,
                work_use_share=share,
                deductible_amount_eur=current_year_amount * share,
            )
        )

    return {slot: tuple(items) for slot, items in items_by_person.items()}


def _load_staking_income_eur_2025(paths: YearPaths) -> Decimal:
    derived_path = structured_input_files(paths)["common_other_income_facts"]
    if not derived_path.exists():
        # Fix: fail closed when the structured derived-facts layer is incomplete.
        # A missing staking-derived-facts file would silently suppress § 22 Nr. 3 income and
        # understate German tax, which is unacceptable for an audit-grade legal engine.
        raise FileNotFoundError(
            "Missing common/other-income-facts.csv; Germany ordinary assessment requires an explicit staking_income_eur row."
        )
    derived_rows = _read_row_csv(derived_path)
    for row in derived_rows:
        if row["key"] == "staking_income_eur":
            return D(row["value"])
    # Fix: require an explicit zero row instead of treating the absence of a staking row as
    # zero. That keeps the inputs layer honest and makes the legal core auditable.
    raise KeyError("staking_income_eur")


def _load_staking_income_allocations_2025(
    paths: YearPaths,
    person_slots: list[dict],
) -> tuple[Decimal, tuple[Decimal, ...]]:
    derived_path = structured_input_files(paths)["common_other_income_facts"]
    if not derived_path.exists():
        raise FileNotFoundError(
            "Missing common/other-income-facts.csv; Germany ordinary assessment requires an explicit staking_income_eur row."
        )
    derived_rows = _read_row_csv(derived_path)
    by_key = {row["key"]: D(row["value"]) for row in derived_rows if row.get("key")}
    allocations = []
    has_explicit_allocations = False
    for person in person_slots:
        key = f"{person['slot']}_staking_income_eur"
        if key in by_key:
            has_explicit_allocations = True
        allocations.append(by_key.get(key, D("0.00")))
    total = by_key.get("staking_income_eur")
    if total is None:
        if has_explicit_allocations:
            total = sum(allocations, D("0.00"))
        else:
            raise KeyError("staking_income_eur")
    return total, tuple(allocations) if has_explicit_allocations else ()


def _required_int_column(value: str, *, label: str) -> int:
    raw = str(value).strip()
    if raw == "":
        # § 31 / § 32 Abs. 6 EStG aggregations cannot run with a missing
        # months count — fail closed (invariant I4 forbids silent zero
        # defaults on declared inputs).
        raise ValueError(f"{label} must be provided as a non-negative integer.")
    parsed = int(raw)
    if parsed < 0:
        raise ValueError(f"{label} must be non-negative.")
    return parsed


def _decimal_or_zero(value: str, *, label: str) -> Decimal:
    raw = str(value).strip()
    if raw == "":
        return D("0.00")
    parsed = D(raw)
    if parsed < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return parsed


def _load_children_2025(paths: YearPaths) -> tuple[Child2025, ...]:
    """Read ``config/children.csv`` into a tuple of typed ``Child2025``.

    The CSV is the shared schema between the German, U.S., and intake
    adapters (see germany_2025_law.py docstring on ``Child2025``). When
    the file is absent the workspace declares no children — return an
    empty tuple, and the Pipeline 1 derivation aggregates to
    ``children_present=False`` so the legal stages short-circuit.

    Authority context: § 31 EStG (Familienleistungsausgleich), § 32
    Abs. 6 EStG (Kinderfreibetrag + BEA), BKGG (Kindergeld).
    https://www.gesetze-im-internet.de/estg/__31.html
    https://www.gesetze-im-internet.de/estg/__32.html
    https://www.gesetze-im-internet.de/bkgg_1996/
    """
    if not paths.children_path.exists():
        return ()
    rows = _read_row_csv(paths.children_path)
    children: list[Child2025] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        child_id = str(row.get("child_id", "")).strip()
        if child_id and child_id in seen_ids:
            raise ValueError(
                f"Duplicate child_id {child_id!r} in config/children.csv "
                f"(row {index})."
            )
        if child_id:
            seen_ids.add(child_id)
        relationship = str(row.get("relationship", "")).strip().lower()
        if relationship not in {"qualifying_child", "qualifying_relative"}:
            raise ValueError(
                f"config/children.csv row {index}: relationship must be "
                "'qualifying_child' or 'qualifying_relative'."
            )
        kindergeld_recipient = str(row.get("kindergeld_recipient", "")).strip().lower()
        if kindergeld_recipient not in {
            "taxpayer",
            "spouse",
            "other_parent",
            "none",
            "",
        }:
            raise ValueError(
                f"config/children.csv row {index}: kindergeld_recipient "
                "must be one of 'taxpayer', 'spouse', 'other_parent', 'none'."
            )
        if kindergeld_recipient == "":
            kindergeld_recipient = "none"
        # Months facts are required so the derivation never silently
        # zeros out (invariant I4); MFS allocation honours kindergeld
        # received columns.
        months_in_household = _required_int_column(
            row.get("months_in_household", ""),
            label=f"config/children.csv row {index}: months_in_household",
        )
        if months_in_household > 12:
            raise ValueError(
                f"config/children.csv row {index}: months_in_household must be in [0, 12]."
            )
        months_in_us_household_raw = str(row.get("months_in_us_household", "")).strip()
        months_in_us_household = (
            _required_int_column(
                months_in_us_household_raw,
                label=f"config/children.csv row {index}: months_in_us_household",
            )
            if months_in_us_household_raw != ""
            else 0
        )
        if months_in_us_household > 12:
            raise ValueError(
                f"config/children.csv row {index}: months_in_us_household must be in [0, 12]."
            )
        annual_gross_income_eur = _decimal_or_zero(
            row.get("annual_gross_income_eur", ""),
            label=f"config/children.csv row {index}: annual_gross_income_eur",
        )
        annual_gross_income_usd = _decimal_or_zero(
            row.get("annual_gross_income_usd", ""),
            label=f"config/children.csv row {index}: annual_gross_income_usd",
        )
        kindergeld_received_eur = _decimal_or_zero(
            row.get("kindergeld_received_eur", ""),
            label=f"config/children.csv row {index}: kindergeld_received_eur",
        )
        disability_raw = str(row.get("disability_gdb", "")).strip()
        disability_gdb = int(disability_raw) if disability_raw else 0
        if disability_gdb < 0 or disability_gdb > 100:
            raise ValueError(
                f"config/children.csv row {index}: disability_gdb must be in [0, 100]."
            )
        # § 33b Abs. 3 Satz 3 EStG erhöhter Pauschbetrag (€7,400) for
        # hilflos / blind / Pflegegrad 4 oder 5 (§ 33b Abs. 6 EStG).
        # Optional CSV column — defaults to False when absent so the
        # CSV schema stays backward-compatible with workspaces that
        # never need the special amount.
        # https://www.gesetze-im-internet.de/estg/__33b.html
        helpless_raw = str(row.get("disability_helpless_or_blind", "")).strip().lower()
        if helpless_raw in {"", "0", "false", "no", "nein"}:
            disability_helpless_or_blind = False
        elif helpless_raw in {"1", "true", "yes", "ja"}:
            disability_helpless_or_blind = True
        else:
            raise ValueError(
                f"config/children.csv row {index}: "
                "disability_helpless_or_blind must be a boolean (true/false/1/0/yes/no/ja/nein) per § 33b Abs. 3 Satz 3 EStG."
            )
        # § 33b Abs. 5 EStG transferral of a child's Behinderten-
        # Pauschbetrag to the parents is wired via Pipeline 1
        # (DERIVE-DE25-CHILDREN aggregates the per-child total) and
        # Pipeline 2 (DE25-BEHINDERUNG-PAUSCHBETRAG adds it to the
        # parents' household total when the profile election
        # ``elections.germany_disability_pauschbetrag_transfer`` is
        # true). The election is validated at the derivation stage
        # boundary; loading the GdB here is unconditional.
        # https://www.gesetze-im-internet.de/estg/__33b.html
        children.append(
            Child2025(
                child_id=child_id,
                name=str(row.get("name", "")).strip(),
                date_of_birth=str(row.get("date_of_birth", "")).strip(),
                ssn=str(row.get("ssn", "")).strip(),
                itin=str(row.get("itin", "")).strip(),
                steuer_id=str(row.get("steuer_id", "")).strip(),
                relationship=relationship,
                months_in_household=months_in_household,
                months_in_us_household=months_in_us_household,
                annual_gross_income_eur=annual_gross_income_eur,
                annual_gross_income_usd=annual_gross_income_usd,
                kindergeld_received_eur=kindergeld_received_eur,
                kindergeld_recipient=kindergeld_recipient,
                disability_gdb=disability_gdb,
                disability_helpless_or_blind=disability_helpless_or_blind,
            )
        )
    return tuple(children)


def load_germany_children_facts_2025(
    paths: YearPaths,
    *,
    filing_posture: str,
) -> GermanyChildrenFacts2025:
    """Load and aggregate children for the German Familienleistungsausgleich.

    Returns an empty (children_present=False) facts object when
    ``config/children.csv`` is missing or contains zero qualifying-child
    rows. The legal stage DE25-CHILDREN-CREDITS
    short-circuits in that case so demo workspaces without children
    keep producing identical numerics.

    Authority: § 31 EStG / § 32 Abs. 6 EStG / BKGG.
    https://www.gesetze-im-internet.de/estg/__31.html
    """
    children = _load_children_2025(paths)
    return aggregate_germany_children_facts_2025(
        children, filing_posture=filing_posture
    )


def _load_germany_prepayments(
    paths: YearPaths,
    person_slots: list[dict],
) -> tuple[Decimal, tuple[Decimal, ...]]:
    payment_rows = _optional_row_csv(paths.payments_path)
    germany_rows = [
        row
        for row in payment_rows
        if row.get("jurisdiction", "").strip().lower() == "germany"
        and row.get("payment_type", "").strip().lower() == "income_tax_prepayment"
    ]
    if not germany_rows:
        return _sum_document_fact(paths, "german_prepayment_pdf", "payment_amount_eur"), ()
    allocations_by_slot = {person["slot"]: D("0.00") for person in person_slots}
    aggregate_total = D("0.00")
    has_person_allocations = False
    for row in germany_rows:
        amount = D(row["amount"])
        currency = row.get("currency", "").strip().upper()
        if amount < D("0.00") or currency != "EUR":
            raise ValueError("German income-tax prepayments must be non-negative EUR amounts.")
        aggregate_total += amount
        person_id = row.get("person_id", "").strip()
        if person_id:
            has_person_allocations = True
            if person_id not in allocations_by_slot:
                raise ValueError(f"Unknown person_id {person_id!r} in config/payments.csv")
            allocations_by_slot[person_id] += amount
    allocations = tuple(allocations_by_slot[person["slot"]] for person in person_slots)
    return aggregate_total, allocations if has_person_allocations else ()


def load_joint_ordinary_inputs_2025(paths: YearPaths) -> JointOrdinaryInputs2025:
    person_slots = load_german_person_slots(paths)
    profile = _profile(paths)
    # § 51a EStG: Kirchensteuer election must be explicit; fail closed if member
    # of a Kirchensteuer-collecting Religionsgemeinschaft (not modeled in 2025).
    _required_germany_kirchensteuer_membership(profile)
    equipment_items_by_person = _load_work_equipment_items_by_person(paths, person_slots)
    thresholds = _decimal_map(paths.reference_data_root / "de-tax-constants.csv")
    # § 22 Nr. 3 Satz 2 EStG and § 32d Abs. 1 / § 20 Abs. 9 / § 4 SolzG 1995
    # rates are statutory; the workspace CSV row is a redundant declaration
    # that must agree with the centralized 2025 constants per invariant I1.
    assert_germany_csv_statutory_constants_2025(thresholds)
    filing_posture = _germany_filing_posture(paths, person_slots)
    staking_income_total, staking_allocations = _load_staking_income_allocations_2025(paths, person_slots)
    prepayments_total, prepayment_allocations = _load_germany_prepayments(paths, person_slots)

    people: list[PersonOrdinaryInputs2025] = []
    for person in person_slots:
        wage = _load_wage_totals(paths, person.get("owner"))
        manual = _person_manual_deductions(paths, person["slot"], wage)
        people.append(
            PersonOrdinaryInputs2025(
                slot=person["slot"],
                order_label=person["order_label"],
                display_name=person.get("display_name", ""),
                owner=person.get("owner"),
                wage=wage,
                work_equipment_items=equipment_items_by_person[person["slot"]],
                home_office_days_without_visit=int(manual["home_office_days_without_first_workplace_visit"]),
                home_office_days_with_visit=int(manual["home_office_days_with_first_workplace_visit"]),
                home_office_visit_days_no_other_workplace=manual[
                    "home_office_first_workplace_visit_days_have_no_other_workplace"
                ],
                manual_work_equipment_deduction_eur=D(str(manual["manual_work_equipment_deduction_eur"])),
                telecom_deduction_eur=D(str(manual["telecom_deduction_eur"])),
                employment_legal_insurance_deduction_eur=D(
                    str(manual["employment_legal_insurance_deduction_eur"])
                ),
                cross_border_tax_help_deduction_eur=D(
                    str(manual["cross_border_tax_help_deduction_eur"])
                ),
                health_insurance_sick_pay_reduction_rate=D(
                    str(manual["health_insurance_sick_pay_reduction_rate"])
                ),
                other_vorsorge_cap_eur=D(str(manual["other_vorsorge_cap_eur"])),
            )
        )

    return JointOrdinaryInputs2025(
        people=tuple(people),
        other_income_22nr3_eur=staking_income_total,
        # § 22 Nr. 3 Satz 2 EStG Freigrenze comes from the law module after the
        # CSV is asserted to match it (assert_germany_csv_statutory_constants_2025).
        other_income_22nr3_threshold_eur=OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR,
        prepayments_eur=prepayments_total,
        filing_posture=filing_posture,
        # § 26 Abs. 1-3 EStG prerequisites are validated in _germany_filing_posture for
        # married_joint before the core law layer may apply § 26b / § 32a Abs. 5 splitting.
        joint_assessment_prerequisites_validated=filing_posture == "married_joint",
        other_income_22nr3_by_person_eur=staking_allocations,
        prepayments_by_person_eur=prepayment_allocations,
    )
