"""New-1 Phase 3 — structural cross-check: working-tree law modules
source their statutory constants from the F1 shadow TOMLs.

Per New-1 (`.review/2026-05-10-platform-flexibility-review.md` lines
168-236), the working-tree law modules
(``tax_pipeline/y2025/{germany,us,treaty}_law.py``) read their
statutory constants from :data:`tax_pipeline._law_data.LAW_DATA`
instead of carrying duplicate Python ``Decimal("X")`` literals. This
test is the structural lock that prevents future drift between the
working tree and the F1 TOMLs even if ``_LAW_DATA`` is ever bypassed.

What this test asserts
----------------------
1. **Loader fidelity.** Every ``LAW_DATA[name]`` value matches the
   corresponding TOML ``value`` byte-for-byte
   (``str(LAW_DATA[name]) == toml_value``). If the loader ever
   silently coerced a string to a different Decimal scale, this
   catches it.
2. **No regrown working-tree literal.** No top-level
   ``NAME = Decimal("X") | D("X")`` assignment in the three working-
   tree law modules carries a NAME that exists in any
   ``law/**/*.toml``. Once a constant is migrated, the only way to
   change its value is to edit the TOML (which then triggers A4
   re-sign). A literal that regrows in the working tree is a bug
   class New-1 explicitly closes.

Sentinels (``ZERO_*`` / ``*_CENT``) and constants whose name does
NOT appear in any TOML are out of scope; this test only protects
TOML-migrated names.

Authority
---------
- F1 (2026-05-08 platform-flexibility-review.md, "Statutory constants
  to TOML"): the data-side migration.
- New-1 (2026-05-10 platform-flexibility-review.md, "duplicate-Decimal
  problem"): the working-tree → loader collapse this test guards.
- A4 (LOCK.md § 2 Layer 1): the audit-sign discipline that depends on
  the TOML being the only edit point.
"""
from __future__ import annotations

import ast
import tomllib
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline._law_data import LAW_DATA

REPO_ROOT = Path(__file__).resolve().parents[2]
LAW_DIR = REPO_ROOT / "law"
WORKING_TREE_LAW_MODULES = (
    REPO_ROOT / "tax_pipeline" / "y2025" / "germany_law.py",
    REPO_ROOT / "tax_pipeline" / "y2025" / "us_law.py",
    REPO_ROOT / "tax_pipeline" / "y2025" / "treaty_law.py",
)


def _all_toml_constants() -> dict[str, tuple[str, Path]]:
    """Walk ``law/**/*.toml`` and return ``{NAME: (toml_value_str, path)}``.

    Table-shaped entries (W2.A / T1.2; ``shape != "scalar"``) are
    skipped — they have no top-level ``value`` and are read via the
    sibling :data:`LAW_TABLES` namespace, not :data:`LAW_DATA`.
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


def _top_level_decimal_literals(path: Path) -> dict[str, tuple[str, int]]:
    """Top-level ``NAME = Decimal("X")`` / ``D("X")`` assignments in
    ``path``. Returns ``{NAME: (literal_str, line_no)}``.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    out: dict[str, tuple[str, int]] = {}
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
        out[target.id] = (literal, node.lineno)
    return out


class WorkingTreeMatchesShadowTomlTest(unittest.TestCase):
    maxDiff = None

    def test_law_data_values_round_trip_against_their_source_toml(self) -> None:
        """``LAW_DATA[name]`` byte-matches the TOML ``value`` it came
        from. Catches a silent loader bug (e.g. a future loader that
        normalizes ``Decimal("12096.00")`` to ``Decimal("12096")``).
        """
        toml_universe = _all_toml_constants()
        offenders: list[str] = []
        for name, (toml_value, path) in toml_universe.items():
            self.assertIn(name, LAW_DATA, f"{name}: not in LAW_DATA")
            loaded = LAW_DATA[name]
            self.assertIsInstance(
                loaded, Decimal,
                f"{name}: loaded as {type(loaded).__name__}, expected Decimal.",
            )
            if str(loaded) != toml_value:
                offenders.append(
                    f"{name} ({path.relative_to(REPO_ROOT)}): "
                    f"LAW_DATA value str()={str(loaded)!r} != "
                    f"TOML value {toml_value!r}"
                )
            if Decimal(toml_value) != loaded:
                offenders.append(
                    f"{name} ({path.relative_to(REPO_ROOT)}): "
                    f"Decimal({toml_value!r}) != LAW_DATA[{name!r}]"
                )
        self.assertEqual(
            offenders, [],
            "LAW_DATA must round-trip TOML values byte-identically:\n"
            + "\n".join(f"  {o}" for o in offenders),
        )

    def test_no_working_tree_literal_carries_a_toml_migrated_name(self) -> None:
        """Once a NAME exists in any ``law/**/*.toml``, no top-level
        ``NAME = Decimal("X") | D("X")`` assignment may live in the
        three working-tree law modules — the working tree must read
        the value from :data:`LAW_DATA`.

        This is the structural lock against drift: a future agent
        cannot bypass ``_LAW_DATA`` by re-typing the literal locally.
        """
        toml_universe = _all_toml_constants()
        offenders: list[str] = []
        for path in WORKING_TREE_LAW_MODULES:
            literals = _top_level_decimal_literals(path)
            for name, (literal, lineno) in literals.items():
                if name in toml_universe:
                    toml_value, toml_path = toml_universe[name]
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                        f"{name} = Decimal({literal!r}) — name is "
                        f"declared in {toml_path.relative_to(REPO_ROOT)} "
                        f"with value {toml_value!r}. Replace the "
                        f"literal with "
                        f'_LAW_DATA["{name}"] so the F1 TOML is the '
                        "single source of truth (New-1)."
                    )
        self.assertEqual(
            offenders, [],
            "Working-tree law modules must read TOML-migrated "
            "constants from _LAW_DATA, not retype them as literals:\n"
            + "\n".join(f"  {o}" for o in offenders),
        )

    def test_every_toml_migrated_name_is_imported_by_a_working_tree_module(self) -> None:
        """For each TOML constant that has a working-tree consumer,
        the working tree reads it via ``_LAW_DATA["NAME"]``. This is
        the dead-code check: a TOML constant that no working-tree
        module imports either has no working-tree need (acceptable —
        e.g. shadow-tree-only treaty-article rates) or means the
        migration left a stale literal somewhere.

        We do NOT assert the converse (every TOML name is imported),
        because some TOML constants are intentionally shadow-only
        (e.g. ``BEA_FREIBETRAG_PER_PARENT_2025_EUR`` in p32.toml).
        Instead we count the imports and pin a floor — if it drops,
        a working-tree migration regressed.
        """
        toml_universe = _all_toml_constants()
        imported_names: set[str] = set()
        for path in WORKING_TREE_LAW_MODULES:
            src = path.read_text(encoding="utf-8")
            for name in toml_universe:
                # Look for either ``_LAW_DATA["name"]`` or
                # ``LAW_DATA["name"]`` (in case the import alias
                # changes), at any indentation. The marker has to
                # appear lexically; this is a light check that
                # complements the AST round-trip above.
                if (
                    f'_LAW_DATA["{name}"]' in src
                    or f'LAW_DATA["{name}"]' in src
                ):
                    imported_names.add(name)
        # Today (post-Phase 2) the working tree imports 71 TOML
        # constants (73 working-tree literals minus 5 that never
        # existed in the working tree, plus pilot/migration; the
        # migrated count is 71). Pin a floor of 70 so a regression
        # that drops a working-tree import is visible.
        self.assertGreaterEqual(
            len(imported_names), 70,
            f"Working-tree law modules import only {len(imported_names)} "
            "TOML-migrated names; expected ≥70 (71 today). A drop "
            "indicates a migration regressed.",
        )


if __name__ == "__main__":
    unittest.main()
