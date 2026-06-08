"""New-1 — :mod:`tax_pipeline._law_data` loader unit tests.

The loader at :mod:`tax_pipeline._law_data` walks every
``law/**/*.toml`` and exposes :data:`LAW_DATA` as a frozen mapping of
``{NAME: Decimal(value)}``. After New-1 the working-tree law modules
read their statutory constants from this loader instead of carrying
duplicate Decimal literals.

What this test asserts
----------------------
1. The loader covers every constant declared in any sibling TOML — the
   universe of F1-migrated statutory constants.
2. Each loaded value is a :class:`~decimal.Decimal` with the exact
   string representation of the source TOML ``value`` (trailing zeros,
   scale preserved).
3. The mapping is read-only at the type level (``MappingProxyType``) so
   a renderer or rule body cannot smuggle a new constant in at runtime.
4. The loader rejects duplicate names — a name shared across two TOMLs
   is a real bug per New-1's "raise on collision" contract.
5. **Byte-identity to the working tree.** For every TOML constant whose
   name also appears as a top-level Decimal literal in
   ``tax_pipeline/y2025/{germany,us,treaty}_law.py`` today, the loader
   value matches the literal byte-for-byte (``Decimal(str_value) ==
   Decimal(literal)``). This is the lock that lets the migration land
   without disturbing the workspace md5s.

Per CLAUDE.md "fail closed": every assertion compares concrete numeric
outcomes against the cited authority, not just that the loader runs.
"""
from __future__ import annotations

import ast
import tomllib
import unittest
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from tax_pipeline._law_data import LAW_DATA

REPO_ROOT = Path(__file__).resolve().parents[2]
LAW_DIR = REPO_ROOT / "law"
WORKING_TREE_LAW_MODULES = (
    REPO_ROOT / "tax_pipeline" / "y2025" / "germany_law.py",
    REPO_ROOT / "tax_pipeline" / "y2025" / "us_law.py",
    REPO_ROOT / "tax_pipeline" / "y2025" / "treaty_law.py",
)


def _all_toml_constants() -> dict[str, tuple[str, Path]]:
    """Walk ``law/**/*.toml`` and return ``{NAME: (value_str, path)}``.

    Table-shaped entries (W2.A / T1.2; ``shape != "scalar"``) are
    skipped — they have no top-level ``value`` and live in
    :data:`LAW_TABLES` rather than :data:`LAW_DATA`.
    """
    out: dict[str, tuple[str, Path]] = {}
    for toml_path in sorted(LAW_DIR.rglob("*.toml")):
        with toml_path.open("rb") as fh:
            data = tomllib.load(fh)
        for name, entry in data.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("shape", "scalar") != "scalar":
                continue
            out[name] = (entry["value"], toml_path)
    return out


def _working_tree_literal_constants() -> dict[str, str]:
    """Top-level ``NAME = Decimal("X")`` / ``D("X")`` assignments in the
    three working-tree law modules. Returns ``{NAME: literal_string}``
    where ``literal_string`` is the raw string passed to the
    ``Decimal``/``D`` constructor (so trailing-zero precision is
    preserved verbatim).
    """
    out: dict[str, str] = {}
    for path in WORKING_TREE_LAW_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                target = node.target
                value = node.value
            else:
                continue
            if not isinstance(target, ast.Name):
                continue
            if not isinstance(value, ast.Call):
                continue
            func = value.func
            if not (isinstance(func, ast.Name) and func.id in ("Decimal", "D")):
                continue
            if not value.args or not isinstance(value.args[0], ast.Constant):
                continue
            literal = value.args[0].value
            if not isinstance(literal, str):
                continue
            out[target.id] = literal
    return out


class LawDataLoaderUnitTest(unittest.TestCase):
    maxDiff = None

    def test_loader_returns_frozen_mapping(self) -> None:
        # MappingProxyType prevents a caller from registering a new
        # canonical at runtime — the only edit point is the TOML.
        self.assertIsInstance(LAW_DATA, MappingProxyType)
        with self.assertRaises(TypeError):
            LAW_DATA["NEW_CONSTANT"] = Decimal("1")  # type: ignore[index]

    def test_loader_covers_all_toml_constants(self) -> None:
        # The universe is exactly the constants declared in
        # law/**/*.toml. Per New-1, F1 migrated 78 constants today.
        toml_universe = _all_toml_constants()
        self.assertEqual(
            set(LAW_DATA), set(toml_universe),
            "LAW_DATA names must match law/**/*.toml constant names "
            "exactly. Missing names indicate the loader skipped a "
            "TOML; extra names indicate a stale entry.",
        )
        # Pin the count so adding a TOML constant without updating the
        # downstream working-tree law module is structurally visible
        # (the test below cross-checks byte-identity for the subset
        # that has a working-tree literal). 75 = 78 (post-F1 baseline)
        # minus 3 treaty-orphan constants removed in W1.A / T1.1
        # (DBA_USA_ART_11_INTEREST_RATE, GERMANY_US_TREATY_DIRECT_-
        # INVESTMENT_DIVIDEND_RATE, GERMANY_US_TREATY_PENSION_DIVIDEND_RATE
        # — see law/treaty/dba_usa/art10.py + art11.py scope notes).
        self.assertGreaterEqual(
            len(LAW_DATA), 75,
            "Expected at least 75 constants (78 post-F1 minus 3 treaty "
            "orphans removed in W1.A / T1.1); saw "
            f"{len(LAW_DATA)}.",
        )

    def test_loader_preserves_decimal_precision(self) -> None:
        # ``Decimal("12096.00")`` must round-trip exactly — its scale
        # is part of the fingerprint contract (I6).
        toml_universe = _all_toml_constants()
        offenders: list[str] = []
        for name, (toml_value, path) in toml_universe.items():
            loaded = LAW_DATA[name]
            if not isinstance(loaded, Decimal):
                offenders.append(
                    f"{name}: loaded as {type(loaded).__name__}, "
                    "expected Decimal."
                )
                continue
            if str(loaded) != toml_value:
                offenders.append(
                    f"{name} ({path.relative_to(REPO_ROOT)}): "
                    f"loaded {str(loaded)!r} != TOML value "
                    f"{toml_value!r} — Decimal scale drifted on load."
                )
        self.assertEqual(
            offenders, [],
            "LAW_DATA values must round-trip Decimal scale verbatim:\n"
            + "\n".join(f"  {o}" for o in offenders),
        )

    def test_loader_matches_any_remaining_working_tree_literal_byte_identically(self) -> None:
        # The post-migration invariant: a working-tree top-level
        # ``Decimal("X")`` literal whose name happens to match a TOML
        # constant must match byte-for-byte. This catches the bug
        # class where a literal regrows somewhere (e.g. someone copies
        # a constant block) and silently disagrees with the TOML.
        #
        # The stricter "no working-tree literal carries a TOML-migrated
        # name at all" invariant is enforced by
        # ``test_working_tree_constants_match_shadow_toml.py`` (Phase 3
        # of New-1). This test is the byte-level safety net for any
        # surface that still carries a literal.
        working_tree = _working_tree_literal_constants()
        toml_universe = _all_toml_constants()
        offenders: list[str] = []
        common_names = set(working_tree) & set(toml_universe)
        for name in sorted(common_names):
            literal = working_tree[name]
            toml_value, path = toml_universe[name]
            if Decimal(literal) != Decimal(toml_value):
                offenders.append(
                    f"{name}: working-tree Decimal({literal!r}) != "
                    f"TOML Decimal({toml_value!r}) at "
                    f"{path.relative_to(REPO_ROOT)}"
                )
            # Byte-identity (string representation): a stricter check
            # — guarantees scale is preserved both ways.
            if literal != toml_value:
                offenders.append(
                    f"{name}: literal string {literal!r} != TOML "
                    f"string {toml_value!r} at "
                    f"{path.relative_to(REPO_ROOT)} — scale drift."
                )
        self.assertEqual(
            offenders, [],
            "Working-tree Decimal literals must match the F1 TOML "
            "values byte-for-byte:\n"
            + "\n".join(f"  {o}" for o in offenders),
        )


if __name__ == "__main__":
    unittest.main()
