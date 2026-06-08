"""Per-form line schema loader (Y2 / P5 from
``.review/2026-05-08-platform-flexibility-review.md``).

Each rendered form (``Form 1040``, ``Schedule 1``, ``Anlage
Vorsorgeaufwand``, …) declares its line numbers and the exact rendered
label strings in a sibling ``tax_pipeline/forms/schemas/<form_id>.toml``
data file. Form renderers in ``tax_pipeline/forms/usa.py`` and
``tax_pipeline/forms/germany.py`` read line labels from the schema via
:func:`load_form_schema` so a 2026 form-line renumber is a TOML edit
rather than a Python-string edit hunt.

Format (one TOML table per form, with an array-of-tables ``[[lines]]``)::

    form_id = "schedule_1"
    form_year = 2025
    display_name = "Schedule 1"
    authority_url = "<official IRS / BMF landing-page URL for the form>"
    canonical_form_name = "Schedule 1"

    [[lines]]
    line_id = "8z"
    label = "Line 8z total"

    [[lines]]
    line_id = "8z_substitute_payments"
    label = "Line 8z statement - substitute payments"
    unused = false  # default; declared lines must have at least one
                     # OutputDeclaration.form_line_refs citation. Set
                     # ``unused = true`` to opt a line out of the I3
                     # bidirectional citation check (with a ``reason``).

The ``label`` field is the *rendered* string the renderer emits to the
``Line`` column in the per-form Markdown table. The ``line_id`` is the
machine-readable identifier used by ``OutputDeclaration.form_line_refs``
``line=`` arguments — the same string that appears in the rule-graph
declaration. ``label`` and ``line_id`` may differ (Form 1040 ``"Line 1h"``
vs. ``line_id="1h"``; Anlage Vorsorgeaufwand ``"Anlage Vorsorgeaufwand
Zeilen 4-9"`` vs. ``line_id="zeilen_4_9"``). The renderer never
constructs the label from ``line_id`` — both are independent fields.

``canonical_form_name`` is the string used by ``FormLineRef.form=`` in
``OutputDeclaration`` declarations, so the I3 cross-check between the
schema and the rule-graph declarations can compare ``(form_id,
line_id)`` directly.

Stdlib only: ``tomllib`` for parsing. Per LOCK.md § 1, helpers under
``tax_pipeline/forms/`` are not audit-locked: this loader is structural
plumbing, not legal math.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_SCHEMAS_ROOT = Path(__file__).parent / "schemas"


@dataclass(frozen=True)
class FormLine:
    """A single declared form-line entry from a form schema."""

    line_id: str
    label: str
    unused: bool = False
    reason: str = ""


@dataclass(frozen=True)
class FormSchema:
    """A loaded form schema (line numbers + labels for one rendered form).

    ``form_id`` matches the schema filename stem (``schedule_1`` ->
    ``schedule_1.toml``). ``canonical_form_name`` is the string used in
    ``FormLineRef(form=...)`` declarations in the rule graph, so the I3
    cross-check between renderer reads and OutputDeclaration citations
    can match by canonical name.
    """

    form_id: str
    form_year: int
    display_name: str
    authority_url: str
    canonical_form_name: str
    lines: tuple[FormLine, ...]

    def find_line(self, line_id: str) -> FormLine:
        """Return the :class:`FormLine` with the given ``line_id``.

        Raises ``KeyError`` if no line with that ``line_id`` is declared
        in the schema. Per CLAUDE.md "fail closed" — a missing line is a
        renderer/schema mismatch, not a default-to-empty situation.
        """
        for line in self.lines:
            if line.line_id == line_id:
                return line
        raise KeyError(
            f"FormSchema[{self.form_id!r}]: no line declared with "
            f"line_id={line_id!r}; declared line_ids: "
            f"{[ln.line_id for ln in self.lines]!r}"
        )

    def label(self, line_id: str) -> str:
        """Convenience: return ``self.find_line(line_id).label``."""
        return self.find_line(line_id).label


def _require_str(table: Mapping[str, object], name: str, *, context: str) -> str:
    value = table.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{context}: required field {name!r} must be a non-empty string"
        )
    return value


def _require_int(table: Mapping[str, object], name: str, *, context: str) -> int:
    value = table.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            f"{context}: required field {name!r} must be an int"
        )
    return value


def load_form_schema(form_id: str) -> FormSchema:
    """Load the form schema for ``form_id`` from
    ``tax_pipeline/forms/schemas/<form_id>.toml``.

    Args:
        form_id: schema filename stem (e.g. ``"schedule_1"``,
            ``"anlage_vorsorgeaufwand"``).

    Returns:
        :class:`FormSchema` with parsed ``lines``.

    Raises:
        FileNotFoundError: if the schema file is missing.
        ValueError: if any required top-level or per-line field is
            missing / wrong type. Per CLAUDE.md "fail closed" — a
            schema with an undeclared label is a structural defect.
    """
    if not isinstance(form_id, str) or not form_id:
        raise ValueError("load_form_schema: form_id must be a non-empty string")
    path = _SCHEMAS_ROOT / f"{form_id}.toml"
    if not path.exists():
        raise FileNotFoundError(
            f"FormSchema[{form_id!r}]: schema file not found at {path}"
        )
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    context = f"FormSchema[{form_id!r}] ({path})"
    declared_form_id = _require_str(data, "form_id", context=context)
    if declared_form_id != form_id:
        raise ValueError(
            f"{context}: declared form_id {declared_form_id!r} does not "
            f"match filename stem {form_id!r}"
        )
    form_year = _require_int(data, "form_year", context=context)
    display_name = _require_str(data, "display_name", context=context)
    authority_url = _require_str(data, "authority_url", context=context)
    canonical_form_name = _require_str(
        data, "canonical_form_name", context=context
    )

    raw_lines = data.get("lines", [])
    if not isinstance(raw_lines, list):
        raise ValueError(
            f"{context}: 'lines' must be a TOML array-of-tables"
        )
    # An empty ``lines = []`` (or a missing ``[[lines]]`` block) is
    # allowed for forms whose Markdown rows are wholly runtime-driven
    # (e.g. Schedule D and Form 8949 emit lines from
    # ``us-capital-results.json`` / ``us-form-8949-income-buckets.csv``
    # with no statically-known line strings). Such schemas declare only
    # the form's display_name + canonical_form_name + authority_url for
    # the title and the I3 cross-check.
    parsed_lines: list[FormLine] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw_lines):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{context}: lines[{index}] must be a TOML table"
            )
        line_context = f"{context} lines[{index}]"
        line_id = _require_str(entry, "line_id", context=line_context)
        if line_id in seen_ids:
            raise ValueError(
                f"{line_context}: duplicate line_id {line_id!r}"
            )
        seen_ids.add(line_id)
        label = _require_str(entry, "label", context=line_context)
        unused_raw = entry.get("unused", False)
        if not isinstance(unused_raw, bool):
            raise ValueError(
                f"{line_context}: 'unused' must be a bool"
            )
        reason_raw = entry.get("reason", "")
        if not isinstance(reason_raw, str):
            raise ValueError(
                f"{line_context}: 'reason' must be a string"
            )
        if unused_raw and not reason_raw.strip():
            raise ValueError(
                f"{line_context}: when unused=true, a non-empty "
                "'reason' is required (citation or rationale)"
            )
        parsed_lines.append(
            FormLine(
                line_id=line_id,
                label=label,
                unused=unused_raw,
                reason=reason_raw,
            )
        )

    return FormSchema(
        form_id=form_id,
        form_year=form_year,
        display_name=display_name,
        authority_url=authority_url,
        canonical_form_name=canonical_form_name,
        lines=tuple(parsed_lines),
    )


def iter_schema_form_ids() -> tuple[str, ...]:
    """Return the sorted tuple of all ``form_id`` values that have a
    declared schema TOML file. Used by the I3 cross-check test to walk
    every declared schema without hardcoding the list.
    """
    if not _SCHEMAS_ROOT.exists():
        return ()
    return tuple(
        sorted(p.stem for p in _SCHEMAS_ROOT.glob("*.toml"))
    )


__all__ = (
    "FormLine",
    "FormSchema",
    "load_form_schema",
    "iter_schema_form_ids",
)
