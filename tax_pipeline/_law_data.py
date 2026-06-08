"""Working-tree statutory-constant loader (New-1 from
``.review/2026-05-10-platform-flexibility-review.md``).

Collapses the duplicate-Decimal layer between
``tax_pipeline/y2025/*_law.py`` (working tree, where the rule graph runs)
and the F1 shadow tree (``law/<juri>/year_2025/<chapter>/p<§>.toml``).
After this loader lands, every statutory constant declared in a TOML
data file is the single source of truth: the working-tree law modules
read the constant via :data:`LAW_DATA` (scalars) or :data:`LAW_TABLES`
(table-shaped schedules per W2.A / T1.2) instead of re-typing the
Decimal literal.

Resolution rule
---------------
The loader walks every ``law/**/*.toml`` data file at import time and
exposes:

* :data:`LAW_DATA` — frozen ``{NAME: Decimal(value)}`` for scalar
  constants (TOML tables with ``value = "..."`` or ``shape = "scalar"``).
* :data:`LAW_TABLES` — frozen ``{NAME: TableValue}`` for table-shaped
  schedules (TOML tables declaring a non-``"scalar"`` ``shape`` per
  W2.A / T1.2; see :mod:`law._utils.constants` for the supported
  shapes).

Names are already prefixed for uniqueness (``KINDERGELD_2025_…``,
``TARIFF_2025_…``, ``DBA_USA_…``, ``FUND_TEILFREISTELLUNG_…``); a
duplicate name across two TOML files OR across the scalar/table
namespaces is treated as a real bug and raises ``ValueError``.

Mirrors the F1 shadow-side loader at :mod:`law._utils.constants`. The
shadow loader is per-§ (each ``p<§>.py`` reads its sibling TOML);
this working-tree loader is repo-wide because the working-tree law
modules are flat (one ``germany_law.py`` carries every Germany
constant). Both loaders use ``Decimal(str_value)`` so trailing-zero
precision (``Decimal("12096.00") != Decimal("12096")``) round-trips
byte-identically through the TOML round-trip.

Usage
-----
::

    from tax_pipeline._law_data import LAW_DATA, LAW_TABLES
    KINDERGELD_2025_MONTHLY_EUR = LAW_DATA["KINDERGELD_2025_MONTHLY_EUR"]
    FUND_TEILFREISTELLUNG_RATES_2025 = dict(LAW_TABLES["FUND_TEILFREISTELLUNG_RATES_2025"])

Re-signing after an update
--------------------------
Editing a TOML value invalidates the A4 audit registry entry for that
file (``.audit/hashes.toml``). Re-sign with::

    python -m law.audit sign law/<juri>/year_2025/<chapter>/p<§>.toml

then verify with ``make check-invariants``. Per CLAUDE.md every
tax-rule constant must remain bound to its controlling legal authority,
which lives in the same TOML table (the ``authority`` and
``citation_url`` fields validated by :mod:`law._utils.constants`).
"""
from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from law._utils.constants import TableValue, load_tables

# ``law/`` lives next to ``tax_pipeline/`` at the repo root. Resolve once
# at import time; the loader is read-only after that.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAW_DIR = _REPO_ROOT / "law"

# Shape selector recognised in a TOML table header. ``scalar`` (or
# absence of the ``shape`` field) keeps the pre-W2.A behaviour: read
# the ``value`` string and Decimal-it. Any non-scalar shape is
# delegated to :func:`law._utils.constants.load_tables`.
_SCALAR_SHAPE = "scalar"


def _is_scalar_entry(entry: dict[str, Any]) -> bool:
    """A TOML table is a scalar constant when ``shape`` is absent or
    equal to ``"scalar"``. Any other ``shape`` value belongs to the
    table-shaped path handled by :data:`LAW_TABLES`.
    """
    return entry.get("shape", _SCALAR_SHAPE) == _SCALAR_SHAPE


def _load_all_constants() -> Mapping[str, Decimal]:
    """Walk every ``law/**/*.toml`` and return the merged scalar constants.

    Per CLAUDE.md "fail closed": a missing ``law/`` tree, an unparseable
    TOML, a duplicate name across two TOMLs, or a malformed scalar entry
    all raise rather than default. A constant declared in a TOML must
    carry its citation (``authority`` + ``citation_url``); see
    :func:`law._utils.constants.load_constants` for the per-§ contract
    that this repo-wide loader delegates to.

    Table-shaped entries (``shape = "dict_str_decimal"`` etc., per W2.A
    / T1.2) are skipped here — they're loaded by :func:`_load_all_tables`
    into the sibling :data:`LAW_TABLES` namespace.
    """
    if not _LAW_DIR.is_dir():
        # The working-tree loader is meaningless without the shadow
        # tree. Fail closed instead of returning an empty dict that
        # would silently let callers fall back to literal defaults.
        raise FileNotFoundError(
            f"law/ directory not found at {_LAW_DIR}; the working-tree "
            "law-data loader requires the shadow tree to be present."
        )
    merged: dict[str, Decimal] = {}
    sources: dict[str, Path] = {}
    for toml_path in sorted(_LAW_DIR.rglob("*.toml")):
        with toml_path.open("rb") as fh:
            data = tomllib.load(fh)
        for name, entry in data.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"{toml_path}: top-level key {name!r} must be a "
                    "table with 'value', 'authority', and "
                    "'citation_url' fields."
                )
            if not _is_scalar_entry(entry):
                # Table-shaped — handled by _load_all_tables.
                continue
            if "value" not in entry:
                raise ValueError(
                    f"{toml_path}: constant {name!r} is missing 'value'."
                )
            value = entry["value"]
            if not isinstance(value, str):
                # Per F1: TOML must store the value as a string so
                # Decimal precision (trailing zeros, explicit scale)
                # round-trips. Native TOML floats / ints are rejected.
                raise ValueError(
                    f"{toml_path}: constant {name!r} 'value' must be a "
                    f"string (got {type(value).__name__}); use "
                    'value = "..." so Decimal precision is preserved.'
                )
            if not entry.get("authority"):
                raise ValueError(
                    f"{toml_path}: constant {name!r} is missing "
                    "'authority' citation."
                )
            if not entry.get("citation_url"):
                raise ValueError(
                    f"{toml_path}: constant {name!r} is missing "
                    "'citation_url'."
                )
            if name in merged:
                # Names collide across two TOMLs — a real bug. Don't
                # paper over by keeping the first one; surface it.
                raise ValueError(
                    f"Duplicate law-data constant {name!r}: declared in "
                    f"{sources[name]} and {toml_path}. Statutory "
                    "constant names must be unique across the shadow "
                    "tree."
                )
            merged[name] = Decimal(value)
            sources[name] = toml_path
    return MappingProxyType(merged)


def _load_all_tables() -> Mapping[str, TableValue]:
    """Walk every ``law/**/*.toml`` and return the merged table-shaped
    statutory constants (W2.A / T1.2).

    Delegates per-shape parsing to
    :func:`law._utils.constants.load_tables` (single source of truth for
    the table-shape contract); this function only fans the walk out
    across every TOML and merges with duplicate-name detection.

    Cross-namespace uniqueness is asserted at the bottom of the module
    (a name declared as both a scalar and a table is a real bug).
    """
    if not _LAW_DIR.is_dir():
        raise FileNotFoundError(
            f"law/ directory not found at {_LAW_DIR}; the working-tree "
            "law-data loader requires the shadow tree to be present."
        )
    merged: dict[str, TableValue] = {}
    sources: dict[str, Path] = {}
    for toml_path in sorted(_LAW_DIR.rglob("*.toml")):
        loaded = load_tables(toml_path)
        for name, value in loaded.items():
            if name in merged:
                raise ValueError(
                    f"Duplicate law-data table {name!r}: declared in "
                    f"{sources[name]} and {toml_path}. Statutory "
                    "table names must be unique across the shadow tree."
                )
            merged[name] = value
            sources[name] = toml_path
    return MappingProxyType(merged)


# Eager load: every reader gets frozen mappings. Re-importing the
# module re-reads the disk, so an in-process TOML edit is visible only
# after a fresh interpreter start (consistent with the rest of the
# engine's load-once / fail-closed posture).
LAW_DATA: Mapping[str, Decimal] = _load_all_constants()
LAW_TABLES: Mapping[str, TableValue] = _load_all_tables()

# Cross-namespace uniqueness — a name declared as both a scalar and a
# table is a real bug, not an "old declaration wasn't removed" benign
# overlap. Fail closed at import time so the offending TOML is fixed
# before any downstream rule reads the value.
_overlap = set(LAW_DATA) & set(LAW_TABLES)
if _overlap:
    raise ValueError(
        "Statutory constant names collide between LAW_DATA (scalar) "
        f"and LAW_TABLES (table-shaped): {sorted(_overlap)!r}. Per W2.A "
        "/ T1.2, each name must be either a scalar or a table — not "
        "both."
    )


__all__ = ("LAW_DATA", "LAW_TABLES")
