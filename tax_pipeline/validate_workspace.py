from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tax_pipeline.analysis_inputs import missing_config_inputs, missing_structured_inputs
from tax_pipeline.year_runtime import resolve_workspace_root, resolve_year_paths


@dataclass
class ValidationReport:
    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_section(self, title: str, lines: list[str]) -> None:
        self.sections.append((title, lines))

    @property
    def ready(self) -> bool:
        return not self.errors


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# H3 — boolean-column validation.
#
# The CSV intake surface accepts only the literal strings ``true`` and
# ``false`` for boolean columns, mirroring the ``true``/``false`` values
# the wizard writes. A typo ("ture"/"yes"/"1"/"True") used to silently
# pass through to the engine because the CSV reader does not know which
# columns are boolean-typed; downstream code applied permissive coercion
# rules that varied by call site, so a typo could change a posture
# without raising. The wizard is now the canonical surface — these
# checks catch the case where a user (or a sync script) edited the CSV
# by hand and made a boolean typo.
#
# The column lists here are the engine's authoritative boolean columns.
# Adding a new boolean column requires extending this set so the
# validation tightens with the schema.
PEOPLE_BOOLEAN_COLUMNS = (
    "us_filer",
    "is_taxpayer",
    "is_spouse",
    "nra_for_us_return",
    "german_statutory_health_with_sick_pay",
    "church_tax_applicable",
)

ELECTIONS_BOOLEAN_KEYS = (
    "enabled",
    "use_treaty_resourcing",
    "elect_joint_return_with_nra_spouse",
    "us_filing_required",
)

VALID_BOOLEAN_VALUES = ("true", "false")


def _check_boolean_columns(
    paths,
    rows: list[dict[str, str]],
    *,
    csv_path: Path,
    columns: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Return a list of ``(label, message)`` errors for any boolean column
    whose value is not exactly ``true`` or ``false``. The empty string is
    tolerated because some rows legitimately omit a column.
    """
    errors: list[tuple[str, str]] = []
    for index, row in enumerate(rows, start=1):
        for column in columns:
            if column not in row:
                continue
            value = (row.get(column) or "").strip()
            if value == "":
                continue
            if value not in VALID_BOOLEAN_VALUES:
                rel = _relative(paths, csv_path)
                errors.append(
                    (
                        f"invalid_boolean:{rel}:{column}",
                        (
                            f"{rel} row {index}: column {column!r} must be "
                            f"'true' or 'false', got {value!r}. "
                            "Use the local intake wizard "
                            "(tax-pipeline-intake) to edit boolean fields — "
                            "the wizard always writes exact 'true'/'false' "
                            "strings."
                        ),
                    )
                )
    return errors


def _check_elections_boolean_values(
    paths, rows: list[dict[str, str]], *, csv_path: Path
) -> list[tuple[str, str]]:
    """Elections rows look like ``(jurisdiction, key, value, ...)``. When
    ``key`` is one of the engine's boolean-typed keys, the ``value``
    column must be ``true`` / ``false`` exactly."""
    errors: list[tuple[str, str]] = []
    for index, row in enumerate(rows, start=1):
        key = (row.get("key") or "").strip()
        value = (row.get("value") or "").strip()
        if key not in ELECTIONS_BOOLEAN_KEYS:
            continue
        if value == "":
            continue
        if value not in VALID_BOOLEAN_VALUES:
            rel = _relative(paths, csv_path)
            errors.append(
                (
                    f"invalid_boolean:{rel}:{key}",
                    (
                        f"{rel} row {index}: election {key!r} must have value "
                        f"'true' or 'false', got {value!r}. "
                        "Use the local intake wizard (tax-pipeline-intake) "
                        "to edit boolean elections — the wizard always "
                        "writes exact 'true'/'false' strings."
                    ),
                )
            )
    return errors


def _relative(paths, path: Path) -> str:
    try:
        return path.relative_to(paths.year_root).as_posix()
    except ValueError:
        return str(path)


def _workspace_command_target(paths) -> str:
    if paths.workspace_root == paths.project_root / "years" / "demo-2025":
        return "demo-2025"
    return str(paths.year)


def _workspace_command_suffix(paths) -> str:
    if _workspace_command_target(paths) == "demo-2025":
        return ""
    default_workspace = Path.home() / "taxes" / str(paths.year)
    if paths.workspace_root == default_workspace:
        return ""
    return f" --workspace {paths.workspace_root}"


def _normalize_germany_posture(text: str) -> str:
    return {
        "single": "single",
        "joint": "married_joint",
        "married_joint": "married_joint",
        "separate": "married_separate",
        "married_separate": "married_separate",
    }.get(text.strip().lower(), text.strip().lower())


def _normalize_usa_posture(text: str) -> str:
    return {
        "single": "single",
        "joint": "married_joint",
        "married_joint": "married_joint",
        "mfj": "married_joint",
        "mfs": "mfs_nra_spouse",
        "mfs_nra_spouse": "mfs_nra_spouse",
    }.get(text.strip().lower(), text.strip().lower())


def build_validation_report(paths) -> ValidationReport:
    report = ValidationReport()

    workspace_lines = [
        f"workspace root: {paths.workspace_root}",
        f"workspace target: {paths.year_root.name}",
        (
            "workspace mode: built-in demo"
            if paths.workspace_root == paths.project_root / "years" / "demo-2025"
            else "workspace mode: private external workspace"
        ),
    ]
    if not paths.workspace_root.exists():
        workspace_lines.append("workspace directory does not exist yet")
        report.errors.append("workspace_missing")
        report.add_section("Workspace", workspace_lines)
        report.add_section(
            "Ready",
            [
                "NOT READY",
                f"Create the workspace first with: python3 -m tax_pipeline.scaffold_year {paths.year}",
            ],
        )
        return report
    report.add_section("Workspace", workspace_lines)

    config_lines: list[str] = []
    missing_config = missing_config_inputs(paths)
    if missing_config:
        for path in missing_config:
            config_lines.append(f"missing: {path.as_posix()}")
        report.errors.extend(f"missing_config:{path.as_posix()}" for path in missing_config)
    else:
        config_lines.append("all required config files are present")

    profile = None
    people_rows: list[dict[str, str]] | None = None
    for path in [
        paths.people_path,
        paths.payments_path,
        paths.elections_path,
    ]:
        if path.exists():
            try:
                _read_csv_rows(path)
            except Exception as exc:
                config_lines.append(f"invalid CSV: {_relative(paths, path)} ({exc})")
                report.errors.append(f"invalid_csv:{_relative(paths, path)}")
    if paths.people_path.exists():
        try:
            people_rows = _read_csv_rows(paths.people_path)
        except Exception:
            people_rows = None
    # H3: boolean-column typo detection.
    #
    # The wizard is now the canonical input surface and always writes
    # the literal strings ``true`` / ``false``. Hand-editing a CSV (or a
    # sync script that picked up a typo) used to slip through silently
    # because downstream coercion is permissive in places. We surface
    # those typos here so ``tax-pipeline-validate`` flags them before
    # the rule graph runs.
    if people_rows is not None:
        for error_id, message in _check_boolean_columns(
            paths,
            people_rows,
            csv_path=paths.people_path,
            columns=PEOPLE_BOOLEAN_COLUMNS,
        ):
            config_lines.append(message)
            report.errors.append(error_id)
    if paths.elections_path.exists():
        try:
            elections_rows = _read_csv_rows(paths.elections_path)
        except Exception:
            elections_rows = None
        if elections_rows is not None:
            for error_id, message in _check_elections_boolean_values(
                paths, elections_rows, csv_path=paths.elections_path
            ):
                config_lines.append(message)
                report.errors.append(error_id)
    for path in [paths.profile_path, paths.manual_overrides_path]:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path == paths.profile_path:
                    profile = payload
            except Exception as exc:
                config_lines.append(f"invalid JSON: {_relative(paths, path)} ({exc})")
                report.errors.append(f"invalid_json:{_relative(paths, path)}")
    report.add_section("Config", config_lines)

    posture_lines: list[str] = []
    if profile is None:
        posture_lines.append("cannot evaluate filing posture until config/profile.json is present and valid")
        report.errors.append("profile_missing_or_invalid")
    else:
        from tax_pipeline.y2025.cross_jurisdiction import read_us_filing_required

        jurisdictions = profile.get("jurisdictions", {})
        germany_enabled = bool(jurisdictions.get("germany", {}).get("enabled", True))
        usa_enabled = bool(jurisdictions.get("usa", {}).get("enabled", True))
        # 26 U.S.C. § 6012 cross-jurisdiction gate: when the user
        # opts out via ``elections.us_filing_required=false`` the
        # engine treats the U.S. side as inapplicable. Surface the
        # combined posture here so reviewers see a single yes/no for
        # whether the U.S. pathway runs.
        # https://www.law.cornell.edu/uscode/text/26/6012
        us_filing_required = read_us_filing_required(profile)
        if not us_filing_required:
            usa_enabled = False
        person_count = len(people_rows or [])
        posture_lines.append(f"germany enabled: {germany_enabled}")
        posture_lines.append(f"us_filing_required: {us_filing_required}")
        posture_lines.append(f"usa enabled: {usa_enabled}")
        posture_lines.append(f"people.csv rows: {person_count}")

        # Inconsistent posture: us_filing_required=false but the workspace
        # still carries a populated ``jurisdictions.usa`` block with a
        # filing posture. Fail closed so the user picks one path
        # rather than silently producing a half-rendered package.
        if not us_filing_required:
            usa_block = jurisdictions.get("usa", {}) if isinstance(jurisdictions, dict) else {}
            if isinstance(usa_block, dict) and usa_block.get("filing_posture"):
                # Tolerate the default scaffold value ``"single"`` but warn
                # the user that the U.S. block is now ignored. The
                # validation is informational, not blocking, because
                # the engine deterministically ignores the block when
                # us_filing_required=false.
                posture_lines.append(
                    "us_filing_required=false: jurisdictions.usa.filing_posture "
                    f"({usa_block.get('filing_posture')!r}) is ignored under 26 U.S.C. § 6012"
                )

        if germany_enabled:
            germany_posture = _normalize_germany_posture(str(jurisdictions.get("germany", {}).get("filing_posture", "")))
            posture_lines.append(f"germany filing posture: {germany_posture}")
            if germany_posture not in {"single", "married_joint", "married_separate"}:
                report.errors.append("unsupported_germany_posture")
                posture_lines.append("unsupported Germany filing posture")
            elif germany_posture == "single" and person_count != 1:
                report.errors.append("invalid_germany_single_people_count")
                posture_lines.append("Germany single filing requires exactly one person row")
            elif germany_posture in {"married_joint", "married_separate"} and person_count != 2:
                report.errors.append("invalid_germany_married_people_count")
                posture_lines.append(f"{germany_posture} requires exactly two person rows")
            elif germany_posture == "married_separate":
                report.errors.append("germany_married_separate_unsupported_surface")
                posture_lines.append("Germany married_separate is blocked beyond the ordinary-law layer in the current public engine")

        if usa_enabled:
            usa_posture = _normalize_usa_posture(str(jurisdictions.get("usa", {}).get("filing_posture", "")))
            posture_lines.append(f"u.s. filing posture: {usa_posture}")
            if usa_posture not in {"single", "mfs_nra_spouse", "married_joint"}:
                report.errors.append("unsupported_usa_posture")
                posture_lines.append("unsupported U.S. filing posture")
            elif usa_posture == "single" and person_count != 1:
                report.errors.append("invalid_usa_single_people_count")
                posture_lines.append("U.S. single filing requires exactly one person row")
            elif usa_posture in {"mfs_nra_spouse", "married_joint"} and person_count != 2:
                report.errors.append("invalid_usa_married_people_count")
                posture_lines.append(f"{usa_posture} requires exactly two person rows")
            elif usa_posture == "married_joint":
                spouse_status = str(profile.get("spouse", {}).get("us_tax_status", "")).strip().lower()
                election = profile.get("elections", {}).get("elect_joint_return_with_nra_spouse")
                if spouse_status == "nra" and election is not True:
                    report.errors.append("missing_joint_nra_election")
                    posture_lines.append(
                        "U.S. married_joint with NRA spouse requires elections.elect_joint_return_with_nra_spouse = true"
                    )

    report.add_section("Posture", posture_lines)

    structured_lines: list[str] = []
    try:
        missing_inputs = missing_structured_inputs(paths)
    except Exception as exc:
        structured_lines.append(f"cannot evaluate structured inputs until config is valid ({exc})")
        report.errors.append("structured_input_validation_blocked")
    else:
        if missing_inputs:
            for path in missing_inputs:
                structured_lines.append(f"missing: {path.as_posix()}")
            report.errors.extend(f"missing_structured:{path.as_posix()}" for path in missing_inputs)
        else:
            structured_lines.append("all required structured inputs are present")
    report.add_section("Structured Inputs", structured_lines)

    facts_lines: list[str] = []
    review_md = paths.facts_root / "REVIEW.md"
    validation_json = paths.facts_root / "validation.json"
    if review_md.exists():
        facts_lines.append(f"facts review present: {_relative(paths, review_md)}")
    else:
        facts_lines.append(f"missing: {_relative(paths, review_md)}")
        report.errors.append("facts_review_missing")
    if validation_json.exists():
        try:
            payload = json.loads(validation_json.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                issues = int(payload.get("issues", 0))
            elif isinstance(payload, list):
                issues = len(payload)
            else:
                raise ValueError("expected object or list")
            facts_lines.append(f"fact validation issues: {issues}")
            if issues:
                report.errors.append("fact_validation_issues")
        except Exception as exc:
            facts_lines.append(f"invalid JSON: {_relative(paths, validation_json)} ({exc})")
            report.errors.append("facts_validation_invalid")
    else:
        facts_lines.append(f"missing: {_relative(paths, validation_json)}")
    report.add_section("Facts Review", facts_lines)

    command_target = _workspace_command_target(paths)
    command_suffix = _workspace_command_suffix(paths)
    ready_lines = ["READY" if report.ready else "NOT READY"]
    if report.ready:
        ready_lines.append(f"Run: python3 -m tax_pipeline.run_year {command_target}{command_suffix}")
    else:
        ready_lines.append(
            f"Fix the items above, then rerun: python3 -m tax_pipeline.validate_workspace {command_target}{command_suffix}"
        )
    report.add_section("Ready", ready_lines)
    return report


def render_validation_report(report: ValidationReport) -> str:
    lines: list[str] = []
    for title, items in report.sections:
        lines.append(title)
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validation_report_payload(report: ValidationReport) -> dict[str, object]:
    groups: dict[str, list[str]] = {
        "missing_config": [],
        "missing_structured": [],
        "other_errors": [],
    }
    for error in report.errors:
        if error.startswith("missing_config:"):
            groups["missing_config"].append(error.split(":", 1)[1])
        elif error.startswith("missing_structured:"):
            groups["missing_structured"].append(error.split(":", 1)[1])
        else:
            groups["other_errors"].append(error)

    sections = [{"title": title, "lines": items} for title, items in report.sections]
    ready_lines = next((items for title, items in report.sections if title == "Ready"), [])
    return {
        "ready": report.ready,
        "errors": list(report.errors),
        "groups": groups,
        "sections": sections,
        "ready_lines": list(ready_lines),
    }


def validate_workspace(project_root: Path, year: str, *, workspace_root: Path | None = None) -> ValidationReport:
    paths = resolve_year_paths(project_root, year, workspace_root=workspace_root)
    return build_validation_report(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("year")
    parser.add_argument("--workspace")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    project_root = Path(__file__).resolve().parent.parent
    workspace_root = Path(args.workspace) if args.workspace else resolve_workspace_root(project_root, args.year)
    report = validate_workspace(project_root, args.year, workspace_root=workspace_root)
    print(render_validation_report(report), end="")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
