"""Per-§ statutory constant loader (F1 from 2026-05-08 platform-flexibility review).

Each ``law/<juri>/year_2025/<chapter>/p<§>.py`` shadow file declares its
statutory numeric constants (rates, thresholds, dollar / euro amounts) in a
sibling ``p<§>.toml`` data file. The shadow ``.py`` reads them at import
time via :func:`load_constants` so a year-on-year roll-forward is "edit the
TOML" rather than "edit the Python literal."

Format (one TOML table per named constant)::

    [KINDERGELD_2025_MONTHLY_EUR]
    value = "255"
    authority = "§ 6 Abs. 2 BKGG"
    citation_url = "https://www.gesetze-im-internet.de/bkgg_1996/__6.html"

The ``value`` field is a *string* — Decimal precision is preserved exactly
(``Decimal("12096.00") != Decimal("12096")`` for fingerprinting). The
``authority`` and ``citation_url`` fields are mandatory: per CLAUDE.md every
tax-rule constant must cite a controlling legal authority, and migrating the
literal must not separate it from its citation.

Per LOCK.md § 1, helpers under ``law/_utils/`` are not audit-locked: this
file is structural plumbing, not legal math.

Table shapes (W2.A / T1.2)
--------------------------
Atomic scalar constants use a top-level ``value = "..."`` field and load
via :func:`load_constants`. Table-shaped statutory constants (rate
schedules, bracket lists, per-cohort tables) declare a ``shape`` field
and load via :func:`load_tables`. Supported shapes:

* ``scalar`` (default if ``shape`` is absent) — :func:`load_constants`
  returns ``{name: Decimal(value)}``.
* ``dict_str_decimal`` — ``{name: dict[str, Decimal]}`` where the table
  has an ``[<NAME>.entries]`` sub-table whose values are Decimal-string
  literals.
* ``dict_int_decimal`` — ``{name: dict[int, Decimal]}``; sub-table keys
  must be parseable as ``int``.
* ``dict_int_decimal_tuple`` — ``{name: dict[int, tuple[Decimal, ...]]}``;
  sub-table values are TOML arrays of Decimal-string literals.
* ``bracket_list`` — ``{name: tuple[BracketRow, ...]}`` where each
  ``[[<NAME>.brackets]]`` array-of-tables entry is exposed as a
  read-only mapping of its Decimal-string fields. The consumer side
  (shadow + working tree) reconstitutes the legacy split-tuple
  structures from this unified record list.

Each of the 4 non-scalar shapes is handled inline in :func:`load_tables`
with a clear if/elif. Per the W2.A brief: "Don't introduce a rich-shape
constant framework — handle 4 shapes inline in the loader with clear
if/elif. Resist generalization." If a 6th shape ever shows up, add
another branch; do not generalize via metaclass / pluggable shape
registry.
"""
from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


# Shape selectors recognised in TOML table headers. ``scalar`` is the
# default when ``shape`` is absent (backward compat with the pre-W2.A
# scalar-only loader). The 4 table shapes are handled by ``load_tables``.
_SHAPE_SCALAR = "scalar"
_SHAPE_DICT_STR_DECIMAL = "dict_str_decimal"
_SHAPE_DICT_INT_DECIMAL = "dict_int_decimal"
_SHAPE_DICT_INT_DECIMAL_TUPLE = "dict_int_decimal_tuple"
_SHAPE_BRACKET_LIST = "bracket_list"

_TABLE_SHAPES = frozenset(
    {
        _SHAPE_DICT_STR_DECIMAL,
        _SHAPE_DICT_INT_DECIMAL,
        _SHAPE_DICT_INT_DECIMAL_TUPLE,
        _SHAPE_BRACKET_LIST,
    }
)


# Public type aliases. Kept narrow on purpose — the loader returns
# exactly these four typed shapes; downstream readers consume the
# concrete type.
DictStrDecimal = Mapping[str, Decimal]
DictIntDecimal = Mapping[int, Decimal]
DictIntDecimalTuple = Mapping[int, tuple[Decimal, ...]]
BracketRow = Mapping[str, Decimal]
BracketList = tuple[BracketRow, ...]
TableValue = DictStrDecimal | DictIntDecimal | DictIntDecimalTuple | BracketList


def _require_citation(path: Path, name: str, entry: dict[str, Any]) -> None:
    """Per CLAUDE.md every constant — atomic or table — carries its
    controlling authority + citation_url. Fail closed if either is
    missing or empty.
    """
    if not entry.get("authority"):
        raise ValueError(
            f"{path}: constant {name!r} is missing 'authority' citation."
        )
    if not entry.get("citation_url"):
        raise ValueError(
            f"{path}: constant {name!r} is missing 'citation_url'."
        )


def _decimal_from_str(path: Path, name: str, field_label: str, raw: Any) -> Decimal:
    """Parse a Decimal-string field, fail closed on non-string input.

    Mirrors the scalar contract: native TOML floats / ints are rejected
    so trailing-zero precision survives the round trip.
    """
    if not isinstance(raw, str):
        raise ValueError(
            f"{path}: constant {name!r} {field_label} must be a string "
            f"(got {type(raw).__name__}); use \"...\" so Decimal "
            "precision is preserved."
        )
    return Decimal(raw)


def load_constants(path: Path | str) -> dict[str, Decimal]:
    """Load atomic scalar statutory constants from a sibling TOML data file.

    Args:
        path: Path to the TOML file. May be passed as ``Path(__file__).with_suffix(".toml")``
            from a shadow ``p<§>.py`` module.

    Returns:
        ``{constant_name: Decimal(value)}`` for every TOML table whose
        ``shape`` is absent or equal to ``"scalar"``. Table-shaped
        constants (``shape = "dict_str_decimal"`` etc.) are silently
        skipped — they belong to :func:`load_tables`.

    Raises:
        FileNotFoundError: if the data file is missing.
        ValueError: if any *scalar* table is missing a required field
            (``value`` / ``authority`` / ``citation_url``) or if the
            ``value`` is not a string. Per CLAUDE.md "fail closed" — a
            constant without its citation is a legal-correctness defect,
            not a default-to-zero situation.
    """
    p = Path(path)
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    out: dict[str, Decimal] = {}
    for name, entry in data.items():
        if not isinstance(entry, dict):
            # Top-level scalar — disallowed; every constant must be a
            # table with value + citation fields.
            raise ValueError(
                f"{p}: top-level key {name!r} must be a table with "
                "'value', 'authority', and 'citation_url' fields."
            )
        shape = entry.get("shape", _SHAPE_SCALAR)
        if shape in _TABLE_SHAPES:
            # Belongs to load_tables; not a scalar.
            continue
        if shape != _SHAPE_SCALAR:
            raise ValueError(
                f"{p}: constant {name!r} declares unknown shape "
                f"{shape!r}. Supported shapes: {_SHAPE_SCALAR!r}, "
                + ", ".join(repr(s) for s in sorted(_TABLE_SHAPES))
            )
        if "value" not in entry:
            raise ValueError(f"{p}: constant {name!r} is missing 'value'.")
        value = entry["value"]
        if not isinstance(value, str):
            # Per CLAUDE.md and the F1 migration brief: TOML must store
            # the value as a string so Decimal precision (trailing zeros,
            # explicit scale) round-trips. Native TOML floats / ints are
            # rejected.
            raise ValueError(
                f"{p}: constant {name!r} 'value' must be a string "
                f"(got {type(value).__name__}); use value = \"...\" so "
                "Decimal precision is preserved."
            )
        _require_citation(p, name, entry)
        out[name] = Decimal(value)
    return out


def load_tables(path: Path | str) -> dict[str, TableValue]:
    """Load table-shaped statutory constants from a sibling TOML data file.

    Companion to :func:`load_constants`. Walks the same TOML, returning
    only the table-shaped entries (those declaring a ``shape`` field
    matching one of the four supported table shapes). Scalar entries
    are skipped — they belong to :func:`load_constants`.

    Each returned value is a frozen view (``MappingProxyType`` for
    dict-shaped tables; a tuple for ``bracket_list``) so a downstream
    caller cannot mutate the loaded structure in-place.

    Raises:
        FileNotFoundError: if the data file is missing.
        ValueError: on malformed table entries (missing ``entries`` /
            ``brackets`` sub-table, non-string Decimal field, missing
            citation, unknown ``shape``).
    """
    p = Path(path)
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    out: dict[str, TableValue] = {}
    for name, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"{p}: top-level key {name!r} must be a table."
            )
        shape = entry.get("shape", _SHAPE_SCALAR)
        if shape == _SHAPE_SCALAR:
            # Scalar — belongs to load_constants.
            continue
        _require_citation(p, name, entry)
        if shape == _SHAPE_DICT_STR_DECIMAL:
            entries = entry.get("entries")
            if not isinstance(entries, dict):
                raise ValueError(
                    f"{p}: table {name!r} (shape={shape!r}) requires an "
                    "[<NAME>.entries] sub-table mapping string keys to "
                    "Decimal-string values."
                )
            row: dict[str, Decimal] = {}
            for k, v in entries.items():
                row[k] = _decimal_from_str(p, name, f"entries.{k}", v)
            out[name] = MappingProxyType(row)
        elif shape == _SHAPE_DICT_INT_DECIMAL:
            entries = entry.get("entries")
            if not isinstance(entries, dict):
                raise ValueError(
                    f"{p}: table {name!r} (shape={shape!r}) requires an "
                    "[<NAME>.entries] sub-table mapping integer-string "
                    "keys to Decimal-string values."
                )
            int_row: dict[int, Decimal] = {}
            for k, v in entries.items():
                try:
                    key_int = int(k)
                except ValueError as exc:
                    raise ValueError(
                        f"{p}: table {name!r} (shape={shape!r}) key "
                        f"{k!r} is not a parseable integer: {exc}"
                    ) from exc
                int_row[key_int] = _decimal_from_str(p, name, f"entries.{k}", v)
            out[name] = MappingProxyType(int_row)
        elif shape == _SHAPE_DICT_INT_DECIMAL_TUPLE:
            entries = entry.get("entries")
            if not isinstance(entries, dict):
                raise ValueError(
                    f"{p}: table {name!r} (shape={shape!r}) requires an "
                    "[<NAME>.entries] sub-table mapping integer-string "
                    "keys to arrays of Decimal-string values."
                )
            tuple_row: dict[int, tuple[Decimal, ...]] = {}
            for k, v in entries.items():
                try:
                    key_int = int(k)
                except ValueError as exc:
                    raise ValueError(
                        f"{p}: table {name!r} (shape={shape!r}) key "
                        f"{k!r} is not a parseable integer: {exc}"
                    ) from exc
                if not isinstance(v, list):
                    raise ValueError(
                        f"{p}: table {name!r} entries.{k} must be a TOML "
                        f"array of Decimal-string values (got "
                        f"{type(v).__name__})."
                    )
                tuple_row[key_int] = tuple(
                    _decimal_from_str(p, name, f"entries.{k}[{i}]", elt)
                    for i, elt in enumerate(v)
                )
            out[name] = MappingProxyType(tuple_row)
        elif shape == _SHAPE_BRACKET_LIST:
            brackets = entry.get("brackets")
            if not isinstance(brackets, list) or not brackets:
                raise ValueError(
                    f"{p}: table {name!r} (shape={shape!r}) requires a "
                    "non-empty [[<NAME>.brackets]] array-of-tables."
                )
            rows: list[BracketRow] = []
            for i, raw_row in enumerate(brackets):
                if not isinstance(raw_row, dict) or not raw_row:
                    raise ValueError(
                        f"{p}: table {name!r} brackets[{i}] must be a "
                        "non-empty table of Decimal-string fields."
                    )
                bracket_row: dict[str, Decimal] = {}
                for field, raw in raw_row.items():
                    bracket_row[field] = _decimal_from_str(
                        p, name, f"brackets[{i}].{field}", raw
                    )
                rows.append(MappingProxyType(bracket_row))
            out[name] = tuple(rows)
        else:
            raise ValueError(
                f"{p}: constant {name!r} declares unknown shape "
                f"{shape!r}. Supported shapes: {_SHAPE_SCALAR!r}, "
                + ", ".join(repr(s) for s in sorted(_TABLE_SHAPES))
            )
    return out


__all__ = (
    "BracketList",
    "BracketRow",
    "DictIntDecimal",
    "DictIntDecimalTuple",
    "DictStrDecimal",
    "TableValue",
    "load_constants",
    "load_tables",
)
