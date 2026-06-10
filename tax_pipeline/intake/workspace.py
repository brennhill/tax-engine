from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.demo_workspace import demo_source_root
from tax_pipeline.intake.state import workspace_metadata
from tax_pipeline.paths import YearPaths
from tax_pipeline.scaffold_year import (
    ELECTIONS_COLUMNS,
    PAYMENTS_COLUMNS,
    PEOPLE_COLUMNS,
    _display_germany_filing_posture,
    _display_usa_filing_posture,
    _normalize_germany_filing_posture,
    _normalize_usa_filing_posture,
    ensure_year_scaffold,
    scaffold_year,
    sync_profile_from_csv_inputs,
)
from tax_pipeline.year_runtime import resolve_year_paths


def resolve_workspace_paths(
    project_root: Path,
    year_token: str,
    workspace_root: Path | None = None,
) -> YearPaths:
    if workspace_root is not None:
        _validate_external_workspace_root(project_root, year_token, workspace_root)
    return resolve_year_paths(project_root, year_token, workspace_root=workspace_root)


def _validate_external_workspace_root(project_root: Path, year_token: str, workspace_root: Path) -> None:
    project_root_resolved = project_root.resolve()
    workspace_resolved = workspace_root.expanduser().resolve()
    if workspace_resolved == project_root_resolved or project_root_resolved in workspace_resolved.parents:
        raise ValueError("Unsafe workspace root: intake workspaces must be outside the repository.")
    if workspace_resolved == Path(workspace_resolved.anchor):
        raise ValueError("Unsafe workspace root: refusing to use a filesystem root.")
    home = Path.home().resolve()
    if workspace_resolved == home:
        raise ValueError("Unsafe workspace root: refusing to use the home directory itself.")
    if workspace_root.exists() and workspace_root.is_symlink():
        raise ValueError("Unsafe workspace root: refusing to use a symlink.")
    if year_token.strip().isdigit() and workspace_resolved.name != year_token.strip():
        raise ValueError("Unsafe workspace root: numeric-year workspaces must end with the year directory.")


def create_workspace(
    project_root: Path,
    year_token: str,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    paths = resolve_workspace_paths(project_root, year_token, workspace_root=workspace_root)
    scaffold_year(
        project_root,
        year_token,
        workspace_root=paths.workspace_root,
        input_fn=lambda _prompt: "y",
    )
    return workspace_metadata(paths)


def open_workspace(
    project_root: Path,
    year_token: str,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    paths = resolve_workspace_paths(project_root, year_token, workspace_root=workspace_root)
    return workspace_metadata(paths)


def materialize_demo_into_workspace(
    project_root: Path,
    year_token: str,
    *,
    workspace_root: Path | None = None,
    demo_name: str = "demo-2025",
) -> dict[str, object]:
    """Copy the synthetic demo workspace into the user's year tree.

    Powers the intake wizard's "Try the demo" first-run path: a new user
    gets a runnable workspace with no manual data entry. The demo lives
    under ``years/<demo-name>/`` in the repo and is copied verbatim to
    the resolved year root; the target year token is preserved so the
    user can rename or roll forward later.
    """
    paths = resolve_workspace_paths(project_root, year_token, workspace_root=workspace_root)
    source = demo_source_root(demo_name=demo_name)
    if paths.year_root.exists():
        shutil.rmtree(paths.year_root)
    paths.year_root.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = paths.year_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)
    paths.ensure_directories()
    return workspace_metadata(paths)


def roll_forward_workspace(
    project_root: Path,
    *,
    source_year: str,
    target_year: str,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    """Scaffold ``target_year`` and copy ``config/`` from ``source_year``.

    Onboarding shortcut for returning users — household, postures, and
    elections survive the year transition; raw documents and outputs do
    not. The target year is scaffolded first so missing config files
    fall back to defaults rather than crashing the loader.

    When ``workspace_root`` is supplied, it points at the *target* year
    directory. The source year is expected to live as a sibling under
    the same parent, so we derive its workspace_root by swapping the
    trailing year token. This matches the standard layout
    (``~/taxes/<year>/``) without requiring the caller to pass two paths.
    """
    target_paths = resolve_workspace_paths(project_root, target_year, workspace_root=workspace_root)
    if workspace_root is not None and target_year.strip().isdigit():
        source_workspace_root = workspace_root.parent / source_year
    else:
        source_workspace_root = workspace_root
    source_paths = resolve_workspace_paths(
        project_root,
        source_year,
        workspace_root=source_workspace_root,
    )
    if not source_paths.year_root.exists():
        raise FileNotFoundError(
            f"Cannot roll forward: source workspace {source_paths.year_root} does not exist."
        )
    scaffold_year(
        project_root,
        target_year,
        workspace_root=target_paths.workspace_root,
        input_fn=lambda _prompt: "y",
    )
    source_config = source_paths.year_root / "config"
    target_config = target_paths.year_root / "config"
    if source_config.is_dir():
        for entry in source_config.iterdir():
            destination = target_config / entry.name
            if entry.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(entry, destination)
            else:
                shutil.copy2(entry, destination)
    return workspace_metadata(target_paths)


def _stringify_bool(value: object) -> str:
    return "true" if bool(value) else "false"


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    # Build CSV text in memory and atomic_write_text it (invariant I9 —
    # unique temp filename + parent fsync) so a concurrent writer or a
    # crash mid-write cannot leave a torn or empty CSV on disk.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    atomic_write_text(path, buffer.getvalue())


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: value or "" for key, value in row.items() if key is not None} for row in csv.DictReader(handle)]


def _parse_bool_text(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _validate_payload(payload: dict[str, object]) -> tuple[str, str]:
    household = payload.get("household", {})
    people = payload.get("people", [])
    if not isinstance(household, dict):
        raise ValueError("household must be an object")
    if not isinstance(people, list):
        raise ValueError("people must be a list")
    for index, person in enumerate(people, start=1):
        if not isinstance(person, dict):
            raise ValueError(f"people[{index}] must be an object")
    marital_status = str(household.get("marital_status_on_dec_31", "")).strip().lower()
    germany_posture = _normalize_germany_filing_posture(str(household.get("germany_filing_posture", "")))
    usa_posture = _normalize_usa_filing_posture(str(household.get("usa_filing_posture", "")))

    if marital_status not in {"single", "married"}:
        raise ValueError("Household marital status must be either 'single' or 'married'.")

    if marital_status == "single":
        if len(people) != 1:
            raise ValueError("A single household must contain exactly one person.")
        if germany_posture != "single" or usa_posture != "single":
            raise ValueError("A single household must use single household filing postures in both jurisdictions.")
    else:
        if len(people) != 2:
            raise ValueError("A married household must contain exactly two people.")
        if germany_posture not in {"married_joint", "married_separate"}:
            raise ValueError("A married household must use a Germany married filing posture.")
        if germany_posture == "married_separate":
            # § 26a EStG requires spouse-specific income and deduction allocation across
            # the full output surface. The intake wizard must fail closed until that exists.
            raise ValueError("Germany married_separate is not supported by the public 2025 pipeline yet.")
        if usa_posture not in {"married_joint", "mfs_nra_spouse"}:
            raise ValueError("A married household must use a supported U.S. married filing posture.")

    return germany_posture, usa_posture


def _people_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for person in payload.get("people", []):
        rows.append(
            {
                "person_id": person.get("person_id", ""),
                "display_name": person.get("display_name", ""),
                "first_name": person.get("first_name", ""),
                "last_name": person.get("last_name", ""),
                "gender": person.get("gender", ""),
                "relationship_role": person.get("relationship_role", ""),
                "elster_order": person.get("elster_order", ""),
                "us_filer": _stringify_bool(person.get("us_filer", False)),
                "is_taxpayer": _stringify_bool(person.get("is_taxpayer", False)),
                "is_spouse": _stringify_bool(person.get("is_spouse", False)),
                "date_of_birth": person.get("date_of_birth", ""),
                "citizenship": person.get("citizenship", ""),
                "country_of_tax_residence": person.get("country_of_tax_residence", ""),
                "german_tax_id": person.get("german_tax_id", ""),
                "us_ssn_or_itin": person.get("us_ssn_or_itin", ""),
                "nra_for_us_return": _stringify_bool(person.get("nra_for_us_return", False)),
                "german_health_insurer": person.get("german_health_insurer", ""),
                "german_statutory_health_with_sick_pay": person.get("german_statutory_health_with_sick_pay", ""),
                "german_other_vorsorge_cap_eur": person.get("german_other_vorsorge_cap_eur", ""),
                "church_tax_applicable": person.get("church_tax_applicable", ""),
            }
        )
    return rows


def _payments_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    payments = payload.get("payments", [])
    if not isinstance(payments, list):
        raise ValueError("payments must be a list")
    for index, payment in enumerate(payments, start=1):
        if not isinstance(payment, dict):
            raise ValueError(f"payments[{index}] must be an object")
        rows.append(
            {
                "jurisdiction": payment.get("jurisdiction", ""),
                "person_id": payment.get("person_id", ""),
                "payment_type": payment.get("payment_type", ""),
                "amount": payment.get("amount", ""),
                "currency": payment.get("currency", ""),
                "source": payment.get("source", ""),
                "note": payment.get("note", ""),
            }
        )
    return rows


def read_household(paths: YearPaths) -> dict[str, object]:
    ensure_year_scaffold(paths)
    people_rows = _read_csv(paths.people_path)
    profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))
    jurisdictions = profile.get("jurisdictions", {})
    elections = profile.get("elections", {})
    household = profile.get("household", {})
    return {
        "household": {
            "marital_status_on_dec_31": household.get("marital_status_on_dec_31", ""),
            "germany_filing_posture": jurisdictions.get("germany", {}).get("filing_posture", ""),
            "usa_filing_posture": jurisdictions.get("usa", {}).get("filing_posture", ""),
        },
        "people": [
            {
                **row,
                "us_filer": _parse_bool_text(row.get("us_filer", "")),
                "is_taxpayer": _parse_bool_text(row.get("is_taxpayer", "")),
                "is_spouse": _parse_bool_text(row.get("is_spouse", "")),
                "nra_for_us_return": _parse_bool_text(row.get("nra_for_us_return", "")),
            }
            for row in people_rows
        ],
        "jurisdictions": {
            "germany": {
                "enabled": bool(jurisdictions.get("germany", {}).get("enabled", False)),
            },
            "usa": {
                "enabled": bool(jurisdictions.get("usa", {}).get("enabled", False)),
                "us_ftc_method": elections.get("us_ftc_method", ""),
                "use_treaty_resourcing": bool(elections.get("use_treaty_resourcing", False)),
                "elect_joint_return_with_nra_spouse": bool(elections.get("elect_joint_return_with_nra_spouse", False)),
            },
        },
    }


def write_household(paths: YearPaths, payload: dict[str, object]) -> dict[str, object]:
    ensure_year_scaffold(paths)
    germany_posture, usa_posture = _validate_payload(payload)
    _write_csv(paths.people_path, PEOPLE_COLUMNS, _people_rows(payload))
    _write_csv(paths.elections_path, ELECTIONS_COLUMNS, _elections_rows(payload, germany_posture, usa_posture))
    sync_profile_from_csv_inputs(paths)
    return workspace_metadata(paths)


def read_payments(paths: YearPaths) -> dict[str, object]:
    ensure_year_scaffold(paths)
    return {"payments": _read_csv(paths.payments_path)}


def write_payments(paths: YearPaths, payload: dict[str, object]) -> dict[str, object]:
    ensure_year_scaffold(paths)
    _write_csv(paths.payments_path, PAYMENTS_COLUMNS, _payments_rows(payload))
    return read_payments(paths)


def _elections_rows(payload: dict[str, object], germany_posture: str, usa_posture: str) -> list[dict[str, object]]:
    household = payload.get("household", {})
    jurisdictions = payload.get("jurisdictions", {})
    germany = jurisdictions.get("germany", {})
    usa = jurisdictions.get("usa", {})

    return [
        {
            "jurisdiction": "household",
            "key": "marital_status_on_dec_31",
            "value": str(household.get("marital_status_on_dec_31", "")).strip().lower(),
            "source": "intake_wizard",
            "note": "Household status collected through the local intake wizard.",
        },
        {
            "jurisdiction": "germany",
            "key": "enabled",
            "value": _stringify_bool(germany.get("enabled", True)),
            "source": "intake_wizard",
            "note": "Whether Germany outputs are enabled for this workspace.",
        },
        {
            "jurisdiction": "germany",
            "key": "filing_posture",
            "value": _display_germany_filing_posture(germany_posture),
            "source": "intake_wizard",
            "note": "Germany filing posture.",
        },
        {
            "jurisdiction": "usa",
            "key": "enabled",
            "value": _stringify_bool(usa.get("enabled", True)),
            "source": "intake_wizard",
            "note": "Whether U.S. outputs are enabled for this workspace.",
        },
        {
            "jurisdiction": "usa",
            "key": "filing_posture",
            "value": _display_usa_filing_posture(usa_posture),
            "source": "intake_wizard",
            "note": "U.S. filing posture.",
        },
        {
            "jurisdiction": "usa",
            "key": "default_filing_status_if_spouse_is_nonresident_alien",
            "value": usa.get("default_filing_status_if_spouse_is_nonresident_alien", ""),
            "source": "intake_wizard",
            "note": "Default U.S. filing posture when the spouse is NRA.",
        },
        {
            "jurisdiction": "usa",
            "key": "us_ftc_method",
            "value": usa.get("us_ftc_method", ""),
            "source": "intake_wizard",
            "note": "Current FTC accounting method.",
        },
        {
            "jurisdiction": "usa",
            "key": "use_treaty_resourcing",
            "value": _stringify_bool(usa.get("use_treaty_resourcing", False)),
            "source": "intake_wizard",
            "note": "Treaty re-sourcing election.",
        },
        {
            "jurisdiction": "usa",
            "key": "elect_joint_return_with_nra_spouse",
            "value": _stringify_bool(usa.get("elect_joint_return_with_nra_spouse", False)),
            "source": "intake_wizard",
            "note": "Explicit election to file a joint U.S. return with an NRA spouse.",
        },
    ]


def write_intake_basics(paths: YearPaths, payload: dict[str, object]) -> dict[str, object]:
    ensure_year_scaffold(paths)
    germany_posture, usa_posture = _validate_payload(payload)

    _write_csv(paths.people_path, PEOPLE_COLUMNS, _people_rows(payload))
    _write_csv(paths.payments_path, PAYMENTS_COLUMNS, _payments_rows(payload))
    _write_csv(paths.elections_path, ELECTIONS_COLUMNS, _elections_rows(payload, germany_posture, usa_posture))
    sync_profile_from_csv_inputs(paths)
    return workspace_metadata(paths)
