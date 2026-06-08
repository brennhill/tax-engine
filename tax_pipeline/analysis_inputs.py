from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from tax_pipeline.paths import YearPaths

D = Decimal

CSV_FIELDS = ["section", "key", "value", "source", "note"]


def required_config_inputs(paths: YearPaths) -> list[Path]:
    return [
        paths.people_path,
        paths.payments_path,
        paths.elections_path,
        paths.profile_path,
        paths.manual_overrides_path,
    ]


def missing_config_inputs(paths: YearPaths) -> list[Path]:
    return [path.relative_to(paths.year_root) for path in required_config_inputs(paths) if not path.exists()]


def structured_input_files(paths: YearPaths) -> dict[str, Path]:
    return {
        "ecb_usd_eur_daily": paths.reference_data_root / "ecb-usd-eur-daily.csv",
        "de_tax_constants": paths.reference_data_root / "de-tax-constants.csv",
        "us_tax_constants": paths.reference_data_root / "us-tax-constants.csv",
        "de_spouse_bank_capital_certificate": paths.facts_root / "de-spouse-bank-capital-certificate.csv",
        "de_loss_carryforwards": paths.facts_root / "de-loss-carryforwards.csv",
        "de_equipment_source_facts": paths.facts_root / "de-equipment-source-facts.csv",
        "us_carryovers_and_payments": paths.facts_root / "us-carryovers-and-payments.csv",
        "usa_income_summary": paths.derived_facts_root / "usa" / "income-summary.csv",
        "usa_foreign_wage_support": paths.derived_facts_root / "usa" / "foreign-wage-support.csv",
        "germany_capital_sales_detail": paths.derived_facts_root / "germany" / "capital-sales-detail.csv",
        "germany_income_cashflows": paths.derived_facts_root / "germany" / "income-cashflows.csv",
        "germany_capital_support": paths.derived_facts_root / "germany" / "capital-support.csv",
        "usa_capital_summary": paths.derived_facts_root / "usa" / "capital-summary.csv",
        "common_other_income_facts": paths.derived_facts_root / "common" / "other-income-facts.csv",
        "usa_ftc_support": paths.derived_facts_root / "usa" / "ftc-support.csv",
        "de_model_assumptions": paths.tax_positions_root / "de-model-assumptions.csv",
        "us_model_assumptions": paths.tax_positions_root / "us-model-assumptions.csv",
    }


def structured_input_paths(paths: YearPaths) -> list[Path]:
    return list(structured_input_files(paths).values())


def missing_structured_inputs(paths: YearPaths) -> list[Path]:
    # Local import to avoid a circular dependency: cross_jurisdiction_2025
    # is a small leaf module and analysis_inputs is imported very early.
    from tax_pipeline.y2025.cross_jurisdiction import read_us_filing_required

    required = structured_input_files(paths)
    if paths.profile_path.exists():
        profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
        jurisdictions = profile.get("jurisdictions", {})
        germany_enabled = bool(jurisdictions.get("germany", {}).get("enabled", True))
        usa_enabled = bool(jurisdictions.get("usa", {}).get("enabled", True))
        # 26 U.S.C. § 6012: ``elections.us_filing_required=false`` is the
        # canonical opt-out; treat it as a U.S. disable for input
        # requirements so the workspace does not need to ship a
        # us-tax-constants.csv etc.
        # https://www.law.cornell.edu/uscode/text/26/6012
        if not read_us_filing_required(profile):
            usa_enabled = False
        person_slots = profile.get("german_return", {}).get("person_slots", [])
        if not germany_enabled:
            for key in [
                "de_tax_constants",
                "de_spouse_bank_capital_certificate",
                "de_loss_carryforwards",
                "de_equipment_source_facts",
                "germany_capital_sales_detail",
                "germany_income_cashflows",
                "germany_capital_support",
                "de_model_assumptions",
                "common_other_income_facts",
            ]:
                required.pop(key, None)
        elif len(person_slots) < 2:
            required.pop("de_spouse_bank_capital_certificate", None)
        if not usa_enabled:
            for key in [
                "us_tax_constants",
                "us_carryovers_and_payments",
                "usa_income_summary",
                "usa_foreign_wage_support",
                "usa_capital_summary",
                "usa_ftc_support",
                "us_model_assumptions",
            ]:
                required.pop(key, None)
    return [path.relative_to(paths.year_root) for path in required.values() if not path.exists()]


def _read_row_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        cleaned_rows: list[dict[str, str]] = []
        for row in csv.DictReader(f):
            cleaned_rows.append({k: (v or "") for k, v in row.items() if k is not None})
        return cleaned_rows


def _write_row_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _group_rows(path: Path) -> list[dict[str, str]]:
    return _read_row_csv(path) if path.exists() else []


def _load_manual_overrides(paths: YearPaths) -> dict[str, object]:
    return json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))


def _equipment_share_rows(paths: YearPaths, de_equipment_amounts: list[dict[str, str]]) -> list[dict[str, str]]:
    manual_overrides = _load_manual_overrides(paths)
    deductions = manual_overrides.get("deductions", {})
    work_use_percentages = deductions.get("work_use_percentages", {})
    if not isinstance(work_use_percentages, dict):
        raise ValueError("manual_overrides.json deductions.work_use_percentages must be an object.")
    configured_persons = deductions.get("persons", {})
    configured_items = {
        str(item).strip()
        for person_config in configured_persons.values()
        if isinstance(person_config, dict)
        for item in person_config.get("work_equipment_items", [])
        if str(item).strip()
    }
    missing_share_items = sorted(configured_items - set(work_use_percentages))
    if missing_share_items:
        # Fix: configured equipment must have explicit work-use shares even before the law layer
        # runs, otherwise this compatibility layer silently hides a missing deduction input.
        raise ValueError(
            "Missing work-use percentages for configured equipment items in manual_overrides.json: "
            + ", ".join(missing_share_items)
        )
    equipment_amount_keys = {
        row["key"].removesuffix("_amount_eur")
        for row in de_equipment_amounts
        if row["key"].endswith("_amount_eur")
    }
    extra_share_items = sorted(
        key
        for key, value in work_use_percentages.items()
        if Decimal(str(value)) != Decimal("0") and key not in equipment_amount_keys
    )
    if extra_share_items:
        # Fix: also fail when config contains active shares for source rows that do not exist.
        raise ValueError(
            "Configured work-use percentages without matching equipment source facts: "
            + ", ".join(extra_share_items)
        )
    equipment_share_rows: list[dict[str, str]] = []
    for amount_row in de_equipment_amounts:
        amount_key = amount_row["key"]
        if not amount_key.endswith("_amount_eur"):
            continue
        base_key = amount_key.removesuffix("_amount_eur")
        if base_key not in work_use_percentages:
            # Fix: equipment-share rows are part of the derived analysis contract, not an optional
            # convenience layer. If a source equipment row exists and the year config omits the
            # work-use share, the pipeline must fail instead of silently dropping the deduction.
            raise ValueError(
                f"Missing work-use percentage for equipment item {base_key!r} in config/manual_overrides.json."
            )
        work_share = Decimal(str(work_use_percentages[base_key]))
        if work_share < Decimal("0.00") or work_share > Decimal("1.00"):
            raise ValueError(
                f"Work-use percentage for equipment item {base_key!r} must be between 0 and 1 inclusive."
            )
        equipment_share_rows.append(
            {
                "section": "equipment",
                "key": f"{base_key}_work_share",
                "value": str(work_share),
                "source": "config/manual_overrides.json",
                "note": f"Work-use percentage for {base_key} sourced from year config.",
            }
        )
    return equipment_share_rows


def _rows_to_decimal_map(rows: list[dict[str, str]]) -> dict[str, Decimal]:
    return {row["key"]: D(row["value"]) for row in rows}


def german_model_rows(paths: YearPaths) -> list[dict[str, str]]:
    inputs = structured_input_files(paths)
    de_constants = _group_rows(inputs["de_tax_constants"])
    de_spouse = _group_rows(inputs["de_spouse_bank_capital_certificate"])
    de_carry = _group_rows(inputs["de_loss_carryforwards"])
    de_equipment_amounts = _group_rows(inputs["de_equipment_source_facts"])
    de_support = _group_rows(inputs["germany_capital_support"])
    de_assumptions = _group_rows(inputs["de_model_assumptions"])
    return de_assumptions + de_support + de_constants + de_spouse + de_carry + de_equipment_amounts + _equipment_share_rows(paths, de_equipment_amounts)


def us_capital_rows(paths: YearPaths) -> list[dict[str, str]]:
    inputs = structured_input_files(paths)
    return (
        _group_rows(inputs["us_carryovers_and_payments"])
        + _group_rows(inputs["usa_income_summary"])
        + _group_rows(inputs["common_other_income_facts"])
        + _group_rows(inputs["usa_capital_summary"])
    )


def us_model_rows(paths: YearPaths) -> list[dict[str, str]]:
    inputs = structured_input_files(paths)
    return (
        _group_rows(inputs["us_tax_constants"])
        + _group_rows(inputs["usa_foreign_wage_support"])
        + _group_rows(inputs["usa_ftc_support"])
        + _group_rows(inputs["us_model_assumptions"])
    )


def load_german_model_inputs(paths: YearPaths) -> dict[str, Decimal]:
    values = _rows_to_decimal_map(german_model_rows(paths))
    # F-DE-1 / Invariant I1: assert the workspace de-tax-constants.csv rows
    # for the four statutory rates/thresholds match the centralized 2025
    # law-module constants. The CSV row is now a redundant declaration; any
    # drift fails closed before the rule graph runs so a workspace edit
    # cannot silently override Bundesrecht.
    # Imported lazily to avoid cycles between analysis_inputs and law modules.
    from tax_pipeline.y2025.germany_law import (
        assert_germany_csv_statutory_constants_2025,
    )

    assert_germany_csv_statutory_constants_2025(values)
    return values


def load_us_capital_inputs(paths: YearPaths) -> dict[str, Decimal]:
    return _rows_to_decimal_map(us_capital_rows(paths))


def load_us_model_inputs(paths: YearPaths) -> dict[str, Decimal]:
    return _rows_to_decimal_map(us_model_rows(paths))
