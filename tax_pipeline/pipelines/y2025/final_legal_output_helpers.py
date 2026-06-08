"""Pure helpers for ``final_legal_output``.

Generic utilities used by the final-legal-output assembly: file readers
(JSON / text / CSV), small comparators, and scalar formatters. All
functions in this module are pure (no module-level state, no I/O side
effects beyond reading the path passed in) and jurisdiction-agnostic.

Architecture review 2026-05-04 §5 Proposal 7 — extracted from the
944-line ``final_legal_output.py`` to make per-jurisdiction collectors
small enough to live in their own modules. The module preserves the
private-name convention (leading underscore) of the original helpers
because they are still package-internal: callers re-export them through
``final_legal_output`` and ``jurisdictions/*_final`` modules so the
public surface of ``final_legal_output`` is unchanged.

The decomposition is byte-stable: every helper here reproduces the
exact behavior it had inside ``final_legal_output`` so the
``final-legal-output.json`` md5s stay identical across all three
production workspaces (brenn-2025, demo-2025, de-only-demo-2025).
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _missing_artifact_error(path: Path) -> FileNotFoundError:
    return FileNotFoundError(f"Missing required final legal output source artifact: {path.name} ({path})")


def _empty_artifact_error(path: Path) -> ValueError:
    return ValueError(f"Required final legal output source artifact is empty: {path.name} ({path})")


def _read_required_json(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if payload is None:
        raise _missing_artifact_error(path)
    return payload


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _read_required_text(path: Path) -> str:
    text = _read_text(path)
    if text is None:
        raise _missing_artifact_error(path)
    return text


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            overflow = row.get(None)
            if overflow and any(str(value or "").strip() for value in overflow):
                raise ValueError(
                    f"Malformed CSV row in {path.name} at line {row_number}: extra column values {overflow!r}"
                )
            rows.append({key: value for key, value in row.items() if key is not None})
        return rows


def _read_required_csv_rows(path: Path, *, allow_empty: bool = False) -> list[dict[str, str]]:
    if not path.exists():
        raise _missing_artifact_error(path)
    rows = _read_csv_rows(path)
    if not rows and not allow_empty:
        raise _empty_artifact_error(path)
    return rows


def _format_decimal(value: Decimal | str) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _require_equal_string(left: object, right: object, *, label: str) -> None:
    if str(left) != str(right):
        raise ValueError(f"U.S. final output mismatch for {label}: {left!r} != {right!r}")


def _require_final_trace_authorities(rows: list[dict[str, str]], path: Path) -> None:
    for row_number, row in enumerate(rows, start=1):
        for column in ("legal_reference", "authority_url"):
            if not str(row.get(column, "")).strip():
                raise ValueError(f"Missing required values for {path.name}: row {row_number}:{column}")


def _projection_dict_rows(raw_rows: object, fieldnames: tuple[str, ...], *, label: str) -> list[dict[str, str]]:
    if not isinstance(raw_rows, list):
        raise ValueError(f"Missing Germany core render projection: {label}")
    projected: list[dict[str, str]] = []
    for index, row in enumerate(raw_rows, start=1):
        if not isinstance(row, list) or len(row) != len(fieldnames):
            raise ValueError(f"Invalid Germany core render projection row for {label} at row {index}")
        projected.append({field: str(value) for field, value in zip(fieldnames, row)})
    return projected


def _require_projected_rows_equal(
    actual_rows: list[dict[str, str]],
    expected_rows: list[dict[str, str]],
    *,
    path_name: str,
) -> None:
    normalized_actual = [{key: str(value) for key, value in row.items()} for row in actual_rows]
    if normalized_actual != expected_rows:
        raise ValueError(f"Germany final output mismatch for {path_name}: CSV rows drifted from core render_projection.elster")


def _require_projected_text_equal(actual: str, expected: object, *, path_name: str) -> None:
    if not isinstance(expected, str) or not expected:
        raise ValueError(f"Missing Germany core render projection text: {path_name}")
    if actual != expected:
        raise ValueError(f"Germany final output mismatch for {path_name}: text drifted from core render_projection.elster")


def _require_us_sidecar_equal(left: object, right: object, *, artifact: str, label: str) -> None:
    if str(left) != str(right):
        raise ValueError(f"U.S. final output mismatch for {artifact}:{label}: {left!r} != {right!r}")
