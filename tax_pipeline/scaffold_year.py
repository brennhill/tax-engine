from __future__ import annotations

import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path
import sys

from tax_pipeline.manifest import write_manifest
from tax_pipeline.paths import (
    ASSET_CLASS_BUCKETS,
    JURISDICTION_BUCKETS,
    RAW_BUCKETS,
    YearPaths,
)
from tax_pipeline.year_runtime import resolve_workspace_root, resolve_year_paths


DEFAULT_PROFILE = {
    "profile": "us_person_in_berlin",
    "description": "Default scaffold for a U.S. person living and working in Berlin, filing in Germany and the United States, with investments primarily held at U.S. brokers.",
    "employment_country": "DE",
    "employment_city": "Berlin",
    "primary_tax_residence": "DE",
    "us_citizen_or_long_term_resident": True,
    "german_return": {
        "required": True,
        "assume_joint_assessment_if_married": True,
        "person_slots": [
            {
                "slot": "person_1",
                "order_label": "Person 1",
                "display_name": "",
                "owner": None,
                "anlage_n_label": "Anlage N (Person 1)",
                "anlage_kap_label": "Anlage KAP - Person 1",
                # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6
                # Sätze 5 und 6 EStG; former 2024 KAP per-bucket lines
                # for Termingeschäfte and Uneinbringlichkeit are removed
                # for VZ 2025. BMF-VERIFIED 2026-05-13.
                "kap_lines": ["4", "17", "19", "20", "23", "41"],
                "kap_raw_lines": [],
                "kap_posture": "Use person 1's foreign-capital package.",
                "kap_notes": ["Optional equity-comp capital sidecars are included in this person's stock-sale line items."],
            },
            {
                "slot": "person_2",
                "order_label": "Person 2",
                "display_name": "",
                "owner": None,
                "anlage_n_label": "Anlage N (Person 2)",
                "anlage_kap_label": "Anlage KAP - Person 2",
                "kap_lines": ["4", "5", "7", "8", "17", "37", "38", "40"],
                "kap_raw_lines": ["5"],
                "kap_posture": "Use person 2's separate bank-certificate capital schedule.",
                "kap_notes": ["The Upvest certificate remains separate from the Schwab reconstruction."],
            },
        ],
    },
    "us_return": {
        "required": True,
        "default_filing_status_if_spouse_is_nonresident_alien": "MFS",
        "treaty_resourcing_common": True,
    },
    "jurisdictions": {
        "germany": {
            "enabled": True,
            "filing_posture": "single",
        },
        "usa": {
            "enabled": True,
            "filing_posture": "single",
        },
    },
    "investment_defaults": {
        "primary_broker_country": "US",
        "other_stock_countries_allowed": True,
        "crypto_supported": True,
        "real_estate_supported": True,
    },
    "taxpayer": {
        "name": "",
        "citizenship": ["US"],
        "germany_tax_resident": True,
    },
    "spouse": {
        "name": "",
        "us_tax_status": "nra",
    },
    "household": {
        "marital_status_on_dec_31": "",
        "germany_filing_status": "",
        "us_filing_status": "",
    },
    "elections": {
        "us_ftc_method": "",
        "use_treaty_resourcing": None,
        "elect_joint_return_with_nra_spouse": False,
        # § 51a EStG — Kirchensteuer membership posture. "none" = not a member;
        # any other value names the Religionsgemeinschaft (e.g. "EVK", "RKK").
        # Currently the engine fails closed for any membership ≠ "none".
        "germany_kirchensteuer_membership": "",
        # 26 U.S.C. § 911 Foreign Earned Income Exclusion election. Currently
        # the engine fails closed if true (path not implemented).
        "elect_section_911_feie": None,
        # U.S.-Germany Totalization Agreement acknowledgment for § 3101(b)(2)
        # Additional Medicare Tax. The engine assumes wages are German-employer
        # wages exempt from U.S. Medicare; setting this to true affirms the
        # assumption. Setting false (or leaving unset) fails closed.
        "acknowledges_totalization_agreement_germany_us": None,
    },
    # Proposal 8: new scaffolds default to the canonical bucket label
    # set (ISO jurisdiction codes + asset classes). Legacy flat names
    # (``germany``/``us``) still validate via ``all_raw_bucket_names``,
    # so existing workspaces' ``profile.raw_buckets`` keep working
    # without migration. New scaffolds carry the canonical names so
    # the workspace is internally consistent with the new directory
    # layout.
    "raw_buckets": [*JURISDICTION_BUCKETS, *ASSET_CLASS_BUCKETS],
}


DEFAULT_MANUAL_OVERRIDES = {
    "treaty_resourcing": {
        "enabled": None,
        "notes": "",
    },
    "fund_classification": {
        "aktienfonds": [],
        "non_aktienfonds": [],
        "fund_types": {},
    },
    "equity_comp": {
        "rsu_wage_in_payroll": None,
        "basis_overrides": [],
    },
    "deductions": {
        "persons": {
            "person_1": {
                "home_office_days_without_first_workplace_visit": 0,
                "home_office_days_with_first_workplace_visit": 0,
                "home_office_first_workplace_visit_days_have_no_other_workplace": False,
                "manual_work_equipment_deduction_eur": "0.00",
                "telecom_deduction_eur": "0.00",
                "employment_legal_insurance_deduction_eur": "0.00",
                "cross_border_tax_help_deduction_eur": "0.00",
                "health_insurance_sick_pay_reduction_rate": "0.04",
                "work_equipment_items": [],
            },
            "person_2": {
                "home_office_days_without_first_workplace_visit": 0,
                "home_office_days_with_first_workplace_visit": 0,
                "home_office_first_workplace_visit_days_have_no_other_workplace": False,
                "manual_work_equipment_deduction_eur": "0.00",
                "telecom_deduction_eur": "0.00",
                "employment_legal_insurance_deduction_eur": "0.00",
                "cross_border_tax_help_deduction_eur": "0.00",
                "health_insurance_sick_pay_reduction_rate": "0.04",
                "work_equipment_items": [],
            },
        },
        "work_use_percentages": {},
    },
    "carryovers": {
        "german": {},
        "us_ftc": {},
    },
}


REFERENCE_DATA_README = """# reference-data

This folder holds cached external reference data that is not extracted from your own documents.

Examples:
- ECB exchange rates
- IRS yearly average exchange rates
- U.S. tax brackets and deduction tables
- German annual tax constants and thresholds
"""

DERIVED_FACTS_README = """# derived-facts

This folder holds computed economic facts derived from source documents plus reference data.

Shared derived-fact names must stay tax-neutral.

Use shared/common names only for economic reality, for example:
- sale lot matching
- currency-converted proceeds and basis
- withholding cashflow timelines

Do not use shared names for law-defined concepts that differ by jurisdiction.

Example:
- Germany can use work-from-home day counts for its Tagespauschale
- the U.S. home-office rules depend on dedicated exclusive-use workspace

Those should not share one generic `home_office_*` derived field unless the field is purely factual
and not a legal conclusion.

Use these subfolders:

- `common/` for shared tax-neutral economic facts
- `germany/` for Germany-specific derived facts
- `usa/` for U.S.-specific derived facts

Examples:
- sale lot matching
- EUR-converted proceeds, basis, and gains
- dividend and withholding cashflow timelines
- summarized capital buckets used by downstream tax logic
"""

DERIVED_COMMON_README = """# common derived-facts

Use this folder only for tax-neutral derived facts that may be consumed by multiple jurisdictions.

Examples:
- currency conversions
- economic income totals
- shared lot-matching outputs
"""

DERIVED_GERMANY_README = """# germany derived-facts

Use this folder for Germany-specific derived facts and Germany-shaped aggregations.

Examples:
- Germany capital sales detail
- Germany income cashflow support
- Germany capital-tax support
"""

DERIVED_USA_README = """# usa derived-facts

Use this folder for U.S.-specific derived facts and U.S.-shaped aggregations.

Examples:
- Form 8949 / Schedule D support summaries
- Form 1116 support files
- income summary files assembled for U.S. return consumers
- foreign wage support for U.S. FTC workpapers
"""

MANUAL_FACTS_README = """# manual-facts

This folder holds reviewed fact overrides for documents that cannot be parsed deterministically yet.

Use one JSON file per source document, named after the generated facts slug, for example:
- `germany_partner_capital_annual_income_statement_pdf.json`

Each file should contain:
- `parser`
- `status`
- `warnings`
- `facts`

Each fact must include:
- `key`
- `value`
- `value_type`
- `unit`
- `confidence`
- `source.file`
- `source.page`
- `source.section`
- `source.snippet`
- `notes`
"""

TAX_POSITIONS_README = """# tax-positions

This folder holds year-specific tax-layer results and intermediate tax positions.

Tax-position names may be jurisdiction-specific and law-loaded.

Examples:
- Germany `Anlage KAP` lines
- U.S. `Form 1116` positions
- treaty re-sourcing allocations
- optional `de-us-treaty-dividend-items.csv` rows for item-level Germany-U.S. treaty Article 10/23 dividend credits
- optional `us-treaty-dividend-items.csv` rows that match the Germany treaty dividend item IDs for IRS Publication 514 treaty re-sourcing

Do not move these names up into shared facts or shared derived facts.

Examples:
- prior-year carryovers consumed as current-year tax inputs
- treaty-supporting allocation outputs
- line-mapped filing positions
- model-level assumptions that belong in the tax layer rather than raw or derived facts
"""

CONFIG_README = """# config

This folder holds year-specific human-maintained configuration.

- `people.csv` is the public-facing identity and filing-role input surface. Use one row per person.
- `payments.csv` holds tax payments and prepayments such as German income-tax prepayments and U.S. estimated payments.
- `elections.csv` holds filing posture and election choices such as Germany joint-assessment posture and U.S. FTC/treaty elections.
- `profile.json` contains annual household and filing context such as marital status, filing status, residency, and recurring tax elections.
- `profile.json` is the engine-facing derived config. It is synchronized from the CSV inputs where possible so the current pipeline can keep reading one canonical JSON file.
- `profile.json` also holds the Germany filing person order in `german_return.person_slots`, in ELSTER submission order.
- `manual_overrides.json` contains year-specific judgment calls and corrections that are not document-derived facts.

These files are separate from `normalized/` because they are not extracted from source documents.

Jurisdiction-specific legal inputs are allowed here.

Examples:
- Germany work-from-home day counts
- Germany sick-pay reduction rate
- U.S. treaty posture
- U.S. FTC filing assumptions

Do not treat these config keys as shared cross-country schema names.

Before entering real filing choices, read the repo documentation:

- `README.md`
- `docs/support-matrix.md`
- `docs/provider-support.md`
"""

PEOPLE_COLUMNS = [
    "person_id",
    "display_name",
    "first_name",
    "last_name",
    "gender",
    "relationship_role",
    "elster_order",
    "us_filer",
    "is_taxpayer",
    "is_spouse",
    "date_of_birth",
    "citizenship",
    "country_of_tax_residence",
    "german_tax_id",
    "us_ssn_or_itin",
    "nra_for_us_return",
    "german_health_insurer",
    "german_statutory_health_with_sick_pay",
    "german_other_vorsorge_cap_eur",
    "church_tax_applicable",
]

PAYMENTS_COLUMNS = [
    "jurisdiction",
    "person_id",
    "payment_type",
    "amount",
    "currency",
    "source",
    "note",
]

ELECTIONS_COLUMNS = [
    "jurisdiction",
    "key",
    "value",
    "source",
    "note",
]


def _split_name(full_name: str) -> tuple[str, str]:
    text = full_name.strip()
    if not text:
        return "", ""
    parts = text.split()
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _write_json_if_missing(path, payload) -> None:
    if path.exists():
        return
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text_if_missing(path, text: str) -> None:
    if path.exists():
        return
    path.write_text(text, encoding="utf-8")


def _write_csv_if_missing(path, columns: list[str], rows: list[dict[str, object]]) -> None:
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _read_csv_rows(path, columns: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({column: (row.get(column) or "").strip() for column in columns})
        return rows


def _stringify_bool(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def _parse_bool_text(value: str) -> bool | None:
    text = value.strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def _normalize_germany_filing_posture(value: str) -> str:
    text = value.strip().lower()
    return {
        "single": "single",
        "joint": "married_joint",
        "married_joint": "married_joint",
        "separate": "married_separate",
        "married_separate": "married_separate",
    }.get(text, text)


def _normalize_usa_filing_posture(value: str) -> str:
    text = value.strip().lower()
    return {
        "single": "single",
        "joint": "married_joint",
        "married_joint": "married_joint",
        "mfj": "married_joint",
        "mfs": "mfs_nra_spouse",
        "mfs_nra_spouse": "mfs_nra_spouse",
    }.get(text, text)


def _display_germany_filing_posture(value: str) -> str:
    text = _normalize_germany_filing_posture(value)
    return {
        "single": "single",
        "married_joint": "joint",
        "married_separate": "separate",
    }.get(text, value.strip().lower())


def _display_usa_filing_posture(value: str) -> str:
    text = _normalize_usa_filing_posture(value)
    return {
        "single": "single",
        "married_joint": "joint",
        "mfs_nra_spouse": "mfs",
    }.get(text, value.strip().lower())


def _prompt(prompt_text: str, input_fn) -> str:
    return input_fn(prompt_text).strip()


def _prompt_bool(prompt_text: str, input_fn) -> bool:
    while True:
        answer = _prompt(prompt_text, input_fn).lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False


def _build_prompted_profile(paths: YearPaths, input_fn) -> dict[str, object]:
    profile = deepcopy(DEFAULT_PROFILE)
    profile["tax_year"] = paths.year
    profile["taxpayer"]["name"] = _prompt(f"Taxpayer full name for {paths.year}: ", input_fn)
    profile["spouse"]["name"] = _prompt(f"Spouse full name for {paths.year} (blank if none): ", input_fn)
    profile["household"]["marital_status_on_dec_31"] = _prompt(
        f"Marital status on Dec 31, {paths.year} (single/married/divorced/etc): ",
        input_fn,
    )
    profile["household"]["germany_filing_status"] = _prompt(
        f"German filing status for {paths.year} (single/joint): ",
        input_fn,
    )
    profile["household"]["us_filing_status"] = _prompt(
        f"U.S. filing status for {paths.year} (single/mfj/mfs/hoh/qss): ",
        input_fn,
    )
    profile["primary_tax_residence"] = _prompt(f"Primary tax residence for {paths.year} (e.g. DE): ", input_fn)
    profile["employment_city"] = _prompt(f"Employment city for {paths.year}: ", input_fn)
    profile["employment_country"] = _prompt(f"Employment country for {paths.year} (e.g. DE): ", input_fn)
    profile["us_citizen_or_long_term_resident"] = _prompt_bool(
        "U.S. citizen or long-term resident? [y/n]: ",
        input_fn,
    )
    profile["elections"]["us_ftc_method"] = _prompt("U.S. FTC method for this year (accrued/paid): ", input_fn)
    profile["elections"]["use_treaty_resourcing"] = _prompt_bool(
        "Use treaty re-sourcing by default? [y/n]: ",
        input_fn,
    )
    profile["german_return"]["person_slots"][0]["display_name"] = profile["taxpayer"]["name"]
    profile["german_return"]["person_slots"][1]["display_name"] = profile["spouse"]["name"]
    profile["german_return"]["person_slots"][0]["owner"] = "person_1"
    profile["german_return"]["person_slots"][1]["owner"] = "person_2"
    # § 26 EStG joint-assessment prerequisites are legal facts, not posture defaults.
    # Leave joint_assessment_prerequisites absent until the user provides them explicitly.
    return profile


def _people_rows_from_profile(profile: dict[str, object]) -> list[dict[str, object]]:
    taxpayer_name = str(profile.get("taxpayer", {}).get("name", "")).strip()
    spouse_name = str(profile.get("spouse", {}).get("name", "")).strip()
    taxpayer_first, taxpayer_last = _split_name(taxpayer_name)
    spouse_first, spouse_last = _split_name(spouse_name)
    primary_residence = str(profile.get("primary_tax_residence", "")).strip()
    taxpayer_citizenship = ",".join(profile.get("taxpayer", {}).get("citizenship", []))
    spouse_is_nra = str(profile.get("spouse", {}).get("us_tax_status", "")).strip().lower() == "nra"
    rows = [
        {
            "person_id": "person_1",
            "display_name": taxpayer_name,
            "first_name": taxpayer_first,
            "last_name": taxpayer_last,
            "gender": "",
            "relationship_role": "taxpayer",
            "elster_order": "1",
            "us_filer": "true",
            "is_taxpayer": "true",
            "is_spouse": "false",
            "date_of_birth": "",
            "citizenship": taxpayer_citizenship,
            "country_of_tax_residence": primary_residence,
            "german_tax_id": "",
            "us_ssn_or_itin": "",
            "nra_for_us_return": "false",
            "german_health_insurer": "",
            "german_statutory_health_with_sick_pay": "",
            "german_other_vorsorge_cap_eur": "",
            "church_tax_applicable": "",
        },
    ]
    if spouse_name:
        rows.append(
            {
                "person_id": "person_2",
                "display_name": spouse_name,
                "first_name": spouse_first,
                "last_name": spouse_last,
                "gender": "",
                "relationship_role": "spouse",
                "elster_order": "2",
                "us_filer": "false",
                "is_taxpayer": "false",
                "is_spouse": "true",
                "date_of_birth": "",
                "citizenship": "",
                "country_of_tax_residence": primary_residence,
                "german_tax_id": "",
                "us_ssn_or_itin": "",
                "nra_for_us_return": _stringify_bool(spouse_is_nra),
                "german_health_insurer": "",
                "german_statutory_health_with_sick_pay": "",
                "german_other_vorsorge_cap_eur": "",
                "church_tax_applicable": "",
            }
        )
    return rows


def _payments_rows_from_profile(profile: dict[str, object]) -> list[dict[str, object]]:
    return []


def _elections_rows_from_profile(profile: dict[str, object]) -> list[dict[str, object]]:
    germany_return = profile.get("german_return", {})
    us_return = profile.get("us_return", {})
    household = profile.get("household", {})
    elections = profile.get("elections", {})
    jurisdictions = profile.get("jurisdictions", {})
    germany = jurisdictions.get("germany", {})
    usa = jurisdictions.get("usa", {})
    germany_filing_posture = _display_germany_filing_posture(
        str(household.get("germany_filing_status", "") or germany.get("filing_posture", ""))
    )
    usa_filing_posture = _display_usa_filing_posture(
        str(household.get("us_filing_status", "") or usa.get("filing_posture", ""))
    )
    return [
        {
            "jurisdiction": "household",
            "key": "marital_status_on_dec_31",
            "value": household.get("marital_status_on_dec_31", ""),
            "source": "config",
            "note": "Household status at year end.",
        },
        {
            "jurisdiction": "germany",
            "key": "enabled",
            "value": _stringify_bool(germany.get("enabled")),
            "source": "config",
            "note": "Whether Germany outputs are enabled for this workspace.",
        },
        {
            "jurisdiction": "germany",
            "key": "filing_posture",
            "value": germany_filing_posture,
            "source": "config",
            "note": "Germany filing posture.",
        },
        {
            "jurisdiction": "usa",
            "key": "enabled",
            "value": _stringify_bool(usa.get("enabled")),
            "source": "config",
            "note": "Whether U.S. outputs are enabled for this workspace.",
        },
        {
            "jurisdiction": "usa",
            "key": "filing_posture",
            "value": usa_filing_posture,
            "source": "config",
            "note": "U.S. filing posture.",
        },
        {
            "jurisdiction": "usa",
            "key": "default_filing_status_if_spouse_is_nonresident_alien",
            "value": us_return.get("default_filing_status_if_spouse_is_nonresident_alien", ""),
            "source": "config",
            "note": "Default U.S. filing posture when the spouse is NRA.",
        },
        {
            "jurisdiction": "usa",
            "key": "us_ftc_method",
            "value": elections.get("us_ftc_method", ""),
            "source": "config",
            "note": "Current FTC accounting method.",
        },
        {
            "jurisdiction": "usa",
            "key": "use_treaty_resourcing",
            "value": _stringify_bool(elections.get("use_treaty_resourcing")),
            "source": "config",
            "note": "Treaty re-sourcing election.",
        },
        {
            "jurisdiction": "usa",
            "key": "elect_joint_return_with_nra_spouse",
            "value": _stringify_bool(elections.get("elect_joint_return_with_nra_spouse")),
            "source": "config",
            "note": "Explicit election to file a joint U.S. return with an NRA spouse.",
        },
    ]


def _sync_profile_from_people_csv(profile: dict[str, object], rows: list[dict[str, str]]) -> bool:
    changed = False
    ordered_rows = sorted(
        [row for row in rows if row.get("person_id")],
        key=lambda row: (int(row["elster_order"]) if row.get("elster_order", "").isdigit() else 999, row["person_id"]),
    )
    if not ordered_rows:
        return changed
    if len(ordered_rows) > 2:
        raise ValueError("Only one-person or two-person households are supported.")

    person_slots = profile.setdefault("german_return", {}).setdefault("person_slots", deepcopy(DEFAULT_PROFILE["german_return"]["person_slots"]))
    existing_slots = {
        slot.get("slot"): deepcopy(slot)
        for slot in person_slots
        if isinstance(slot, dict) and slot.get("slot")
    }
    slot_templates = {slot["slot"]: deepcopy(slot) for slot in DEFAULT_PROFILE["german_return"]["person_slots"]}
    synced_slots = []
    for index, row in enumerate(ordered_rows, start=1):
        slot_id = row["person_id"] or f"person_{index}"
        slot = existing_slots.get(slot_id) or slot_templates.get(slot_id, {"slot": slot_id})
        slot["slot"] = slot_id
        slot["order_label"] = f"Person {index}"
        slot["display_name"] = row["display_name"]
        slot["owner"] = slot_id
        synced_slots.append(slot)
    if person_slots != synced_slots:
        profile["german_return"]["person_slots"] = synced_slots
        changed = True

    taxpayer_row = next((row for row in rows if _parse_bool_text(row.get("is_taxpayer", "")) is True), None)
    spouse_row = next((row for row in rows if _parse_bool_text(row.get("is_spouse", "")) is True), None)
    if taxpayer_row is None and rows:
        taxpayer_row = rows[0]
    if spouse_row is None and len(rows) > 1:
        spouse_row = rows[1]

    taxpayer = profile.setdefault("taxpayer", {})
    spouse = profile.setdefault("spouse", {})
    if taxpayer_row is not None:
        if taxpayer.get("name", "") != taxpayer_row.get("display_name", ""):
            taxpayer["name"] = taxpayer_row.get("display_name", "")
            changed = True
        citizenship = [part.strip() for part in taxpayer_row.get("citizenship", "").split(",") if part.strip()]
        if taxpayer.get("citizenship", []) != citizenship:
            taxpayer["citizenship"] = citizenship
            changed = True
    if spouse_row is not None:
        if spouse.get("name", "") != spouse_row.get("display_name", ""):
            spouse["name"] = spouse_row.get("display_name", "")
            changed = True
        spouse_status = "nra" if _parse_bool_text(spouse_row.get("nra_for_us_return", "")) else spouse.get("us_tax_status", "")
        if spouse_status != spouse.get("us_tax_status", ""):
            spouse["us_tax_status"] = spouse_status
            changed = True
    else:
        if spouse.get("name", "") != "":
            spouse["name"] = ""
            changed = True
        if spouse.get("us_tax_status", "") != "":
            spouse["us_tax_status"] = ""
            changed = True

    if taxpayer_row is not None and taxpayer_row.get("country_of_tax_residence", ""):
        if profile.get("primary_tax_residence", "") != taxpayer_row["country_of_tax_residence"]:
            profile["primary_tax_residence"] = taxpayer_row["country_of_tax_residence"]
            changed = True
    return changed


def _sync_profile_from_elections_csv(profile: dict[str, object], rows: list[dict[str, str]]) -> bool:
    changed = False
    by_pair = {(row["jurisdiction"], row["key"]): row["value"] for row in rows if row.get("jurisdiction") and row.get("key")}
    household = profile.setdefault("household", {})
    german_return = profile.setdefault("german_return", {})
    us_return = profile.setdefault("us_return", {})
    elections = profile.setdefault("elections", {})
    jurisdictions = profile.setdefault(
        "jurisdictions",
        deepcopy(DEFAULT_PROFILE["jurisdictions"]),
    )

    def set_if_changed(container: dict, key: str, value: object) -> None:
        nonlocal changed
        if value == "" or value is None:
            return
        if container.get(key) != value:
            container[key] = value
            changed = True

    set_if_changed(household, "marital_status_on_dec_31", by_pair.get(("household", "marital_status_on_dec_31"), ""))
    germany_filing_status_raw = by_pair.get(("germany", "filing_posture"), by_pair.get(("germany", "filing_status"), ""))
    us_filing_status_raw = by_pair.get(("usa", "filing_posture"), by_pair.get(("usa", "filing_status"), ""))
    germany_filing_posture = _normalize_germany_filing_posture(germany_filing_status_raw)
    us_filing_posture = _normalize_usa_filing_posture(us_filing_status_raw)
    set_if_changed(household, "germany_filing_status", germany_filing_status_raw.strip().lower())
    set_if_changed(household, "us_filing_status", us_filing_status_raw.strip().lower())
    germany_enabled = _parse_bool_text(by_pair.get(("germany", "enabled"), ""))
    if germany_enabled is not None:
        set_if_changed(jurisdictions.setdefault("germany", {}), "enabled", germany_enabled)
    if germany_filing_posture:
        set_if_changed(jurisdictions.setdefault("germany", {}), "filing_posture", germany_filing_posture)
    usa_enabled = _parse_bool_text(by_pair.get(("usa", "enabled"), ""))
    if usa_enabled is not None:
        set_if_changed(jurisdictions.setdefault("usa", {}), "enabled", usa_enabled)
    if us_filing_posture:
        set_if_changed(jurisdictions.setdefault("usa", {}), "filing_posture", us_filing_posture)
    joint_assessment = _parse_bool_text(by_pair.get(("germany", "assume_joint_assessment_if_married"), ""))
    if joint_assessment is None and germany_filing_posture:
        joint_assessment = germany_filing_posture == "married_joint"
    if joint_assessment is not None:
        set_if_changed(german_return, "assume_joint_assessment_if_married", joint_assessment)
    # § 26 EStG prerequisites must not be synthesized from a CSV filing-posture row.
    # The law loader validates explicit prerequisites before computing a joint return.
    set_if_changed(
        us_return,
        "default_filing_status_if_spouse_is_nonresident_alien",
        by_pair.get(("usa", "default_filing_status_if_spouse_is_nonresident_alien"), ""),
    )
    set_if_changed(elections, "us_ftc_method", by_pair.get(("usa", "us_ftc_method"), ""))
    treaty_resourcing = _parse_bool_text(by_pair.get(("usa", "use_treaty_resourcing"), ""))
    if treaty_resourcing is not None:
        set_if_changed(elections, "use_treaty_resourcing", treaty_resourcing)
    elect_joint_with_nra_spouse = _parse_bool_text(by_pair.get(("usa", "elect_joint_return_with_nra_spouse"), ""))
    if elect_joint_with_nra_spouse is not None:
        set_if_changed(elections, "elect_joint_return_with_nra_spouse", elect_joint_with_nra_spouse)
    return changed


def sync_profile_from_csv_inputs(paths: YearPaths) -> bool:
    if not paths.profile_path.exists():
        raise FileNotFoundError(f"Workspace profile does not exist yet: {paths.profile_path}")

    profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
    changed = False
    changed |= _sync_profile_from_people_csv(profile, _read_csv_rows(paths.people_path, PEOPLE_COLUMNS))
    changed |= _sync_profile_from_elections_csv(profile, _read_csv_rows(paths.elections_path, ELECTIONS_COLUMNS))
    if changed:
        paths.profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return changed


def ensure_year_scaffold(paths: YearPaths, *, prompt_if_config_missing: bool = False, input_fn=input) -> None:
    paths.ensure_directories()
    paths.manual_facts_root.mkdir(parents=True, exist_ok=True)
    paths.config_root.mkdir(parents=True, exist_ok=True)
    paths.reference_data_root.mkdir(parents=True, exist_ok=True)
    paths.derived_facts_root.mkdir(parents=True, exist_ok=True)
    paths.tax_positions_root.mkdir(parents=True, exist_ok=True)

    profile_created = not paths.profile_path.exists()
    people_created = not paths.people_path.exists()
    payments_created = not paths.payments_path.exists()
    elections_created = not paths.elections_path.exists()

    if profile_created:
        if prompt_if_config_missing:
            paths.profile_path.write_text(json.dumps(_build_prompted_profile(paths, input_fn), indent=2) + "\n", encoding="utf-8")
        else:
            payload = deepcopy(DEFAULT_PROFILE)
            payload["tax_year"] = paths.year
            paths.profile_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))

    _write_csv_if_missing(paths.people_path, PEOPLE_COLUMNS, _people_rows_from_profile(profile))
    _write_csv_if_missing(paths.payments_path, PAYMENTS_COLUMNS, _payments_rows_from_profile(profile))
    _write_csv_if_missing(paths.elections_path, ELECTIONS_COLUMNS, _elections_rows_from_profile(profile))

    changed = False
    should_sync_profile = profile_created or not people_created or not elections_created
    if should_sync_profile:
        changed |= _sync_profile_from_people_csv(profile, _read_csv_rows(paths.people_path, PEOPLE_COLUMNS))
        changed |= _sync_profile_from_elections_csv(profile, _read_csv_rows(paths.elections_path, ELECTIONS_COLUMNS))
    if changed:
        paths.profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    if not paths.manual_overrides_path.exists():
        _write_json_if_missing(paths.manual_overrides_path, DEFAULT_MANUAL_OVERRIDES)

    _write_text_if_missing(paths.config_root / "README.md", CONFIG_README)
    _write_text_if_missing(paths.manual_facts_root / "README.md", MANUAL_FACTS_README)
    _write_text_if_missing(paths.reference_data_root / "README.md", REFERENCE_DATA_README)
    _write_text_if_missing(paths.derived_facts_root / "README.md", DERIVED_FACTS_README)
    _write_text_if_missing(paths.derived_facts_root / "common" / "README.md", DERIVED_COMMON_README)
    _write_text_if_missing(paths.derived_facts_root / "germany" / "README.md", DERIVED_GERMANY_README)
    _write_text_if_missing(paths.derived_facts_root / "usa" / "README.md", DERIVED_USA_README)
    _write_text_if_missing(paths.tax_positions_root / "README.md", TAX_POSITIONS_README)


def scaffold_year(
    project_root: Path,
    year: str,
    *,
    workspace_root: Path,
    input_fn=input,
) -> YearPaths:
    if year.startswith("demo-"):
        raise ValueError("The built-in demo workspace is already scaffolded and should not be scaffolded again.")

    paths = resolve_year_paths(project_root, year, workspace_root=workspace_root)
    if not paths.workspace_root.exists():
        answer = input_fn(
            f"Workspace for {paths.year} does not exist yet: {paths.workspace_root}\nCreate it now? [y/N]: "
        ).strip().lower()
        if answer not in {"y", "yes"}:
            raise SystemExit(1)

    ensure_year_scaffold(paths)
    write_manifest(paths.raw_root, paths.manifest_path, year=paths.year)
    workspace_suffix = ""
    default_workspace = resolve_workspace_root(project_root, year)
    if paths.workspace_root != default_workspace:
        workspace_suffix = f" --workspace {paths.workspace_root}"
    print(f"Workspace scaffolded at {paths.workspace_root}")
    print("Next steps:")
    print("1. Edit config/people.csv, config/payments.csv, and config/elections.csv")
    print("2. Drop raw documents into raw/")
    print(f"3. Run: python3 -m tax_pipeline.validate_workspace {year}{workspace_suffix}")
    print(f"4. Run: python3 -m tax_pipeline.run_year {year}{workspace_suffix}")
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("year")
    parser.add_argument("--workspace")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    project_root = Path(__file__).resolve().parent.parent
    workspace_root = (
        Path(args.workspace)
        if args.workspace
        else resolve_workspace_root(project_root, args.year)
    )
    scaffold_year(project_root, args.year, workspace_root=workspace_root, input_fn=input)


if __name__ == "__main__":
    main()
