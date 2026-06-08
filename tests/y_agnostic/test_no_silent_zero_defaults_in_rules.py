"""Invariant I4: no silent zero defaults on declared rule inputs.

Per the project CLAUDE.md "Tax-Law Rule Requirements":

    If a legal source is unclear, year-specific, conflicting, missing, or
    not yet modeled, fail closed with an explicit error or `not_applicable`;
    never silently default to zero.

A `Mapping.get(key, ZERO_USD)` call inside a `calculate(facts)` body silently
substitutes a legally meaningful zero when an upstream stage failed to
populate the key. That's a fail-OPEN posture: the resulting tax number is
indistinguishable from a real zero, but it actually means "the input I
needed was missing." H5 of the 2026-05-01 correctness review documented
exactly this failure mode in
``treaty_2025_rules.treaty25_17_german_residual_cap``: a missing
``de.treaty.us_source_dividend_tax_and_credit`` propagated as a zero
residual cap, silently denying the additional foreign tax credit.

The fix is to subscript with ``facts[key]`` (which raises ``KeyError``)
or to thread the key through ``stage.input_fact_keys`` so the executor
raises ``KeyError("missing input facts")`` before calculate runs.

This test AST-scans the four 2025 rule modules and rejects any
``Call(func=Attribute(attr='get'), args=[<str>, <zero-sentinel>])``.
Lines tagged ``# pragma: nzd-allow <reason>`` are exempt.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PIPELINE_DIR = REPO_ROOT / "tax_pipeline"

def _discover_rule_files() -> tuple[Path, ...]:
    """Auto-discover every ``*_2025_rules.py`` rule module under
    ``tax_pipeline/`` so adding a new rule module (e.g.,
    ``germany_children_2025_rules.py``) is automatically scanned by I4
    without a hand-edit here.
    """
    return tuple(sorted(TAX_PIPELINE_DIR.glob("*_2025_rules.py")))


RULE_FILES = _discover_rule_files()

# Sentinel names that, when used as a `.get(key, default)` default, count as
# a silent zero default. Includes both the canonical ``ZERO_*`` constants
# and bare-int / bare-float zero literals.
ZERO_NAMES = frozenset({"ZERO_USD", "ZERO_EUR"})

# Decimal-constructor argument strings that mean zero.
ZERO_DECIMAL_STR_ARGS = frozenset({"0", "0.00", "0.0"})

# Allow-list pragma marker. A trailing comment of the form
# ``# pragma: nzd-allow <reason>`` exempts the line.
ALLOW_PRAGMA = "pragma: nzd-allow"


def _is_zero_default(node: ast.AST) -> bool:
    """Return True if ``node`` is a literal-zero default value.

    Matches:
      - ``Decimal("0")``, ``Decimal("0.00")``, ``Decimal("0.0")``
      - ``Decimal()``                       (zero-arg Decimal constructor)
      - ``D("0")``, ``D("0.00")``, ``D("0.0")``
      - ``ZERO_USD``, ``ZERO_EUR``
      - ``0``, ``0.0`` (bare numeric literals)
    """
    if isinstance(node, ast.Constant):
        if node.value == 0 or node.value == 0.0:
            return True
        return False
    if isinstance(node, ast.Name):
        return node.id in ZERO_NAMES
    if isinstance(node, ast.Call):
        func = node.func
        func_name: str | None = None
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr
        if func_name not in {"Decimal", "D"}:
            return False
        if not node.args:
            # ``Decimal()`` — the zero-arg constructor returns Decimal('0').
            return True
        if len(node.args) != 1:
            return False
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value in ZERO_DECIMAL_STR_ARGS
        return False
    return False


def _is_string_literal_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _line_has_allow_pragma(source_lines: list[str], lineno: int) -> bool:
    if lineno < 1 or lineno > len(source_lines):
        return False
    return ALLOW_PRAGMA in source_lines[lineno - 1]


def _format_default(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable>"


def _is_facts_get_call(node: ast.AST) -> bool:
    """True iff ``node`` is ``<x>.get(<string-literal>)`` (one or two args).

    Used to recognise the LHS of `facts.get("k") or ZERO_*` and
    `coalesce(facts.get("k"), 0)`-style silent-zero patterns.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "get":
        return False
    if not node.args:
        return False
    return _is_string_literal_key(node.args[0])


def _is_none_compare(node: ast.AST, target_name: str | None = None) -> bool:
    """True iff ``node`` is ``<expr> is not None`` or ``<expr> is None``.

    If ``target_name`` is given, also requires the compared expression
    to be a Name(id=target_name) so we can match the
    ``value if value is not None else ZERO_USD`` shape.
    """
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    if not isinstance(node.ops[0], (ast.Is, ast.IsNot)):
        return False
    cmp = node.comparators[0]
    if not (isinstance(cmp, ast.Constant) and cmp.value is None):
        return False
    if target_name is None:
        return True
    return isinstance(node.left, ast.Name) and node.left.id == target_name


# Function names commonly used to coalesce a possibly-None value with a
# default. ``coalesce(facts.get("k"), 0)`` and equivalents must fail
# closed for declared rule inputs.
COALESCE_FUNC_NAMES = frozenset({"coalesce", "first_not_none", "value_or"})


def _format_node(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable>"


def _scan_file(path: Path) -> list[str]:
    """Return a list of human-readable offender strings."""
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    offenders: list[str] = []

    def _record(lineno: int, snippet_node: ast.AST, kind: str) -> None:
        if _line_has_allow_pragma(source_lines, lineno):
            return
        rel = path.relative_to(REPO_ROOT)
        offenders.append(f"{rel}:{lineno}: {kind}: {_format_node(snippet_node)}")

    for node in ast.walk(tree):
        # Pattern 1 (original): ``facts.get("k", ZERO_*)`` /
        # ``facts.get("k", Decimal("0"))`` etc.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) == 2
            and _is_string_literal_key(node.args[0])
            and _is_zero_default(node.args[1])
        ):
            _record(node.lineno, node, ".get(<key>, <zero>)")
            continue

        # Pattern 2: ``facts.get("k") or ZERO_*`` (BoolOp Or whose left
        # operand is a string-keyed get and whose right operand is a
        # zero sentinel).
        if (
            isinstance(node, ast.BoolOp)
            and isinstance(node.op, ast.Or)
            and len(node.values) == 2
            and _is_facts_get_call(node.values[0])
            and _is_zero_default(node.values[1])
        ):
            _record(node.lineno, node, "<get(...)> or <zero>")
            continue

        # Pattern 3: ``value if value is not None else ZERO_*``.
        # Also catches the inverted ``ZERO_* if value is None else value``.
        if isinstance(node, ast.IfExp):
            test = node.test
            body = node.body
            orelse = node.orelse
            # Form A: ``value if value is not None else ZERO_*``
            if (
                isinstance(body, ast.Name)
                and isinstance(test, ast.Compare)
                and isinstance(test.ops[0], ast.IsNot)
                and _is_none_compare(test, target_name=body.id)
                and _is_zero_default(orelse)
            ):
                _record(node.lineno, node, "<v> if <v> is not None else <zero>")
                continue
            # Form B: ``ZERO_* if value is None else value``
            if (
                isinstance(orelse, ast.Name)
                and isinstance(test, ast.Compare)
                and isinstance(test.ops[0], ast.Is)
                and _is_none_compare(test, target_name=orelse.id)
                and _is_zero_default(body)
            ):
                _record(node.lineno, node, "<zero> if <v> is None else <v>")
                continue

        # Pattern 4: ``coalesce(facts.get("k"), 0)`` and the same shape
        # under common helper names (``first_not_none``, ``value_or``).
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in COALESCE_FUNC_NAMES
            and len(node.args) == 2
            and _is_facts_get_call(node.args[0])
            and _is_zero_default(node.args[1])
        ):
            _record(node.lineno, node, f"{node.func.id}(<get(...)>, <zero>)")
            continue

    return offenders


class NoSilentZeroDefaultsInRulesTest(unittest.TestCase):
    """Per CLAUDE.md: never silently default to zero. Use ``facts[key]``
    so a missing input raises ``KeyError`` and the executor surfaces it
    as a stage failure instead of fabricating a legally meaningful zero.
    """

    def test_no_silent_zero_defaults(self) -> None:
        offenders: list[str] = []
        for rule_file in RULE_FILES:
            self.assertTrue(rule_file.exists(), f"missing rule file: {rule_file}")
            offenders.extend(_scan_file(rule_file))
        self.assertEqual(
            offenders,
            [],
            "Silent zero-default `.get(key, ZERO_*)` calls found in rule "
            "calculate bodies. Per CLAUDE.md (\"never silently default to "
            "zero\"), replace each with `facts[key]` so a missing input "
            "fails closed via KeyError, OR add the key to the stage's "
            "input_fact_keys so the executor raises before calculate runs. "
            "If the input is genuinely optional, mark the line with "
            "`# pragma: nzd-allow <reason>`. Offenders:\n  "
            + "\n  ".join(offenders),
        )


class SilentZeroPatternExtractorTest(unittest.TestCase):
    """Unit tests for the I4 detector — proves every silent-zero shape is caught.

    We write a synthetic snippet to a temp file, run ``_scan_file``, and
    assert at least one offender is found. Without these tests, a
    regression in the detector itself would silently pass the
    integration test (which only asserts "no offenders" on the real
    rule files).
    """

    def _scan(self, snippet: str) -> list[str]:
        # Place the temp file inside the repo so ``path.relative_to(REPO_ROOT)``
        # succeeds (the offender-string formatter uses repo-relative paths).
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(REPO_ROOT), encoding="utf-8"
        ) as f:
            f.write(snippet)
            tmp_path = Path(f.name)
        try:
            return _scan_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_classic_get_zero_default_caught(self) -> None:
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = facts.get("de.k", Decimal("0"))\n'
            '    return x\n'
        )
        self.assertTrue(offenders)

    def test_get_or_zero_pattern_caught(self) -> None:
        # Pattern: facts.get("k") or ZERO_USD
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = facts.get("us.k") or ZERO_USD\n'
            '    return x\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_get_or_decimal_zero_pattern_caught(self) -> None:
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = facts.get("de.k") or Decimal("0.00")\n'
            '    return x\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_value_if_not_none_else_zero_pattern_caught(self) -> None:
        # Pattern: value if value is not None else ZERO_USD
        offenders = self._scan(
            'def calculate(facts):\n'
            '    value = facts.get("us.k")\n'
            '    x = value if value is not None else ZERO_USD\n'
            '    return x\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_zero_if_value_none_else_value_pattern_caught(self) -> None:
        # Inverted ternary: ZERO_USD if value is None else value
        offenders = self._scan(
            'def calculate(facts):\n'
            '    value = facts.get("us.k")\n'
            '    x = ZERO_USD if value is None else value\n'
            '    return x\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_coalesce_with_zero_default_caught(self) -> None:
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = coalesce(facts.get("de.k"), 0)\n'
            '    return x\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_value_or_helper_caught(self) -> None:
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = value_or(facts.get("us.k"), Decimal("0"))\n'
            '    return x\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_pragma_allowlist_suppresses_offender(self) -> None:
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = facts.get("de.k") or ZERO_USD  # pragma: nzd-allow truly optional\n'
            '    return x\n'
        )
        self.assertEqual(offenders, [])

    def test_non_zero_default_not_flagged(self) -> None:
        offenders = self._scan(
            'def calculate(facts):\n'
            '    x = facts.get("de.k", Decimal("1.00"))\n'
            '    return x\n'
        )
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
