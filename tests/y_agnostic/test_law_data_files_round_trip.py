"""F1 — Constants migrated to TOML round-trip cleanly back to Decimal.

Per F1 of ``.review/2026-05-08-platform-flexibility-review.md``, every
``law/<juri>/year_2025/<chapter>/p<§>.py`` shadow file that previously
declared statutory constants as Python ``Decimal(...)`` literals now reads
them from a sibling ``p<§>.toml`` data file via
:func:`law._utils.constants.load_constants`.

This test asserts:

1. Every TOML data file under ``law/`` parses cleanly.
2. Every constant in a TOML file has the three required fields
   (``value``, ``authority``, ``citation_url``) — citation discipline
   never separates from the value (CLAUDE.md).
3. Each ``value`` round-trips: ``str(Decimal(value))`` matches the TOML
   string verbatim, so Decimal precision is preserved exactly (the
   ``Decimal("12096.00") != Decimal("12096")`` invariant for fingerprint
   stability).
4. ``citation_url`` is a non-empty ``https://`` URL.
5. Every constant declared in a sibling ``p<§>.toml`` is imported by the
   ``p<§>.py`` shadow file (no orphan constants).

The migration target is shadow-only; the working tree
(``tax_pipeline/y2025/*_law.py``) keeps its Python ``Decimal(...)``
literals as part of the canonical declaration sites enforced by I1.
"""
from __future__ import annotations

import tomllib
import unittest
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAW_DIR = REPO_ROOT / "law"


def _iter_toml_data_files() -> tuple[Path, ...]:
    """Every ``p<§>.toml`` / ``art<NN>.toml`` data file under ``law/``."""
    if not LAW_DIR.exists():
        return ()
    out = []
    for toml_file in LAW_DIR.rglob("*.toml"):
        # Test fixtures (if any) aren't in scope; the migration target is
        # the shadow tree only.
        out.append(toml_file)
    return tuple(out)


class LawDataFilesRoundTripTest(unittest.TestCase):
    maxDiff = None

    def test_at_least_one_data_file_exists(self) -> None:
        # F1 migration scope: at minimum the BKGG p6 pilot landed.
        self.assertGreaterEqual(
            len(_iter_toml_data_files()), 1,
            "F1 expects at least one law TOML data file to exist after "
            "migration — none found.",
        )

    def test_every_data_file_parses_and_round_trips(self) -> None:
        offenders: list[str] = []
        for path in _iter_toml_data_files():
            rel = path.relative_to(REPO_ROOT)
            try:
                with path.open("rb") as fh:
                    data = tomllib.load(fh)
            except tomllib.TOMLDecodeError as exc:
                offenders.append(f"{rel}: TOML parse error — {exc}")
                continue
            if not data:
                # Citation-only TOML (no numeric constants but the
                # comment header carries the article's authority URL +
                # a scope note). Legitimate after a constant is removed
                # per a "wire or remove" pass (W1.A / T1.1) when the
                # sibling .py file still wants the citation surface.
                continue
            for name, entry in data.items():
                if not isinstance(entry, dict):
                    offenders.append(
                        f"{rel}::{name}: top-level scalar — must be a "
                        "table with value/authority/citation_url."
                    )
                    continue
                # Table-shaped entries (W2.A / T1.2) carry a ``shape``
                # field naming a non-scalar shape. They MUST still carry
                # authority + citation_url (the citation discipline
                # applies to every named statutory constant — atomic or
                # table) but the per-entry ``value`` / Decimal round-
                # trip checks below are scalar-only.
                shape = entry.get("shape", "scalar")
                is_table = shape != "scalar"
                required_fields = (
                    ("authority", "citation_url")
                    if is_table
                    else ("value", "authority", "citation_url")
                )
                # 1. Required fields.
                for required in required_fields:
                    if required not in entry or entry[required] in (None, ""):
                        offenders.append(
                            f"{rel}::{name}: missing or empty '{required}'."
                        )
                if is_table:
                    # Per-shape sub-table validation lives in
                    # :func:`law._utils.constants.load_tables`; this
                    # round-trip test only sanity-checks the top-level
                    # citation envelope and the ``citation_url`` shape.
                    url = entry.get("citation_url", "")
                    if isinstance(url, str) and not url.startswith("https://"):
                        offenders.append(
                            f"{rel}::{name}: citation_url must be an "
                            f"https:// URL (got {url!r})."
                        )
                    continue
                if "value" not in entry:
                    continue
                value = entry["value"]
                # 2. value must be a string (Decimal precision).
                if not isinstance(value, str):
                    offenders.append(
                        f"{rel}::{name}: 'value' must be a string "
                        f"(got {type(value).__name__}); native TOML "
                        "floats/ints would lose Decimal precision."
                    )
                    continue
                # 3. Decimal round-trip — Decimal(value) constructed from
                # the string preserves the literal scale.
                try:
                    decimal_value = Decimal(value)
                except Exception as exc:  # noqa: BLE001 — surface any
                    offenders.append(
                        f"{rel}::{name}: 'value' {value!r} is not a "
                        f"valid Decimal: {exc}"
                    )
                    continue
                # The TOML 'value' string must match the literal Decimal
                # would have used in Python: ``Decimal("X")`` so
                # ``str(Decimal(value)) == value`` for the canonical
                # forms we use (255, 12096.00, 0.0253). Decimal does
                # preserve trailing zeros across str/Decimal round-trips,
                # so a drift between value and str(Decimal(value)) means
                # the TOML carries a non-canonical form.
                if str(decimal_value) != value:
                    offenders.append(
                        f"{rel}::{name}: round-trip drift — "
                        f"value={value!r} but str(Decimal(value))="
                        f"{str(decimal_value)!r}; pin the TOML 'value' "
                        "to the canonical Decimal string form."
                    )
                # 4. citation_url shape.
                url = entry.get("citation_url", "")
                if isinstance(url, str) and not url.startswith("https://"):
                    offenders.append(
                        f"{rel}::{name}: citation_url must be an "
                        f"https:// URL (got {url!r})."
                    )
        self.assertEqual(
            offenders, [],
            "Law TOML data files failed validation:\n  "
            + "\n  ".join(offenders),
        )

    def test_every_toml_constant_is_imported_by_sibling_py(self) -> None:
        """Every constant in a ``p<§>.toml`` is imported by ``p<§>.py``.

        Catches the dead-code class: a constant that lives in the data
        file but no shadow ``.py`` reads it, so the citation lives but the
        rule body silently bypasses it.
        """
        offenders: list[str] = []
        for toml_path in _iter_toml_data_files():
            py_path = toml_path.with_suffix(".py")
            if not py_path.exists():
                offenders.append(
                    f"{toml_path.relative_to(REPO_ROOT)}: no sibling "
                    f"{py_path.name} found."
                )
                continue
            with toml_path.open("rb") as fh:
                data = tomllib.load(fh)
            py_source = py_path.read_text(encoding="utf-8")
            for name, entry in data.items():
                # Scalar constants are read via ``_CONSTANTS["NAME"]``;
                # table-shaped constants (W2.A / T1.2) are read via
                # ``_TABLES["NAME"]``. Either idiom satisfies the "no
                # orphan constants" invariant.
                if isinstance(entry, dict) and entry.get("shape", "scalar") != "scalar":
                    lookup_options = (f'_TABLES["{name}"]',)
                else:
                    lookup_options = (f'_CONSTANTS["{name}"]',)
                if not any(option in py_source for option in lookup_options):
                    offenders.append(
                        f"{toml_path.relative_to(REPO_ROOT)}::{name}: "
                        f"sibling {py_path.name} does not read this "
                        f"constant via any of: "
                        + ", ".join(lookup_options)
                    )
        self.assertEqual(
            offenders, [],
            "Law TOML constants without a matching sibling .py "
            "consumer:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
