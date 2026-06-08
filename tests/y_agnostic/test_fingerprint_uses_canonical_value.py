from __future__ import annotations

"""Invariant I6 — fingerprint payloads use canonical values, never repr().

Audit-trail invariant for § 32d Abs. 5 EStG: StageResult fingerprints
must canonicalize Decimal/Mapping/dataclass values via
tax_pipeline.core.facts._fingerprintable. Stringifying via repr()
collapses canonical equality (Decimal('1.00') vs Decimal('1.0') differ
under repr but are legally identical) and breaks audit reproducibility.

Two-part enforcement:
1. AST grep: no stable_fingerprint(...) call tree contains repr(...).
2. Schema: stable_fingerprint() rejects keys ending in '_repr' or
   starting with 'repr_' so the bug class cannot recur silently.

Authority: § 32d Abs. 5 EStG,
https://www.gesetze-im-internet.de/estg/__32d.html (prior fix in
commit 628082e applied the canonical helper to capital + US rules).
"""

import ast
import unittest
from pathlib import Path

from tax_pipeline.core.facts import stable_fingerprint


REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PIPELINE_DIR = REPO_ROOT / "tax_pipeline"


def _contains_repr_call(node: ast.AST) -> bool:
    """True iff the subtree contains a Call(func=Name('repr'))."""
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "repr"
        ):
            return True
    return False


def _contains_fstring_repr_conversion(node: ast.AST) -> bool:
    """True iff the subtree contains an f-string formatted-value with the
    ``!r`` conversion (i.e., ``f"{x!r}"``).

    The CPython AST emits ``conversion=114`` for ``!r`` (the integer
    code for the ASCII byte 'r'). ``!s`` is 115, ``!a`` is 97, ``-1``
    means no conversion.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.FormattedValue) and child.conversion == ord("r"):
            return True
    return False


def _contains_format_call(node: ast.AST) -> bool:
    """True iff the subtree contains a top-level ``format(x, "...")``
    call (the builtin), which canonicalises a Decimal via the format
    spec rather than passing the Decimal itself.
    """
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "format"
            and len(child.args) >= 1
        ):
            return True
    return False


def _contains_str_of_normalize(node: ast.AST) -> bool:
    """True iff the subtree contains ``str(<expr>.normalize())``.

    ``.normalize()`` collapses canonical-equivalent Decimals into a
    single representative (e.g., ``Decimal('1.00').normalize()`` is
    ``Decimal('1')``), so wrapping a fingerprint payload value in
    ``str(.normalize())`` is exactly the canonical-collapse bug that
    repr() also creates.
    """
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not (isinstance(child.func, ast.Name) and child.func.id == "str"):
            continue
        if not child.args:
            continue
        inner = child.args[0]
        if not isinstance(inner, ast.Call):
            continue
        if (
            isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "normalize"
        ):
            return True
    return False


_NON_CANONICAL_DETECTORS: tuple[
    tuple[str, callable], ...  # type: ignore[type-arg]
] = (
    ("repr(...)", _contains_repr_call),
    ('f"{x!r}"', _contains_fstring_repr_conversion),
    ("format(x, ...)", _contains_format_call),
    ("str(x.normalize())", _contains_str_of_normalize),
)


def _non_canonical_kinds(node: ast.AST) -> list[str]:
    return [name for name, fn in _NON_CANONICAL_DETECTORS if fn(node)]


class FingerprintCanonicalValueTest(unittest.TestCase):
    """Invariant I6: fingerprint payloads carry canonical values, not repr()."""

    def test_no_non_canonical_call_inside_stable_fingerprint_argument_tree(self) -> None:
        offenders: list[str] = []
        for py_file in TAX_PIPELINE_DIR.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not (isinstance(node.func, ast.Name) and node.func.id == "stable_fingerprint"):
                    continue
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    kinds = _non_canonical_kinds(arg)
                    if kinds:
                        offenders.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}: "
                            f"stable_fingerprint(...) wraps non-canonical value "
                            f"({', '.join(kinds)}); pass the canonical value "
                            "directly so _fingerprintable can canonicalize it."
                        )
                        break
        self.assertEqual(
            offenders,
            [],
            "Invariant I6 violated — stable_fingerprint must receive canonical "
            "values, never repr-stringified, !r-formatted, format()-coerced, "
            "or .normalize()-collapsed ones (§ 32d Abs. 5 EStG audit "
            "trail). Offenders:\n" + "\n".join(offenders),
        )

    def test_stable_fingerprint_rejects_repr_shadow_keys(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "fingerprint payload must use canonical 'value' field"
        ):
            stable_fingerprint({"foo_repr": "bar"})
        with self.assertRaisesRegex(
            ValueError, "fingerprint payload must use canonical 'value' field"
        ):
            stable_fingerprint({"repr_foo": "bar"})
        # Sanity: canonical payloads still work.
        digest = stable_fingerprint({"fact_key": "x", "value": "y"})
        self.assertEqual(len(digest), 64)


class NonCanonicalDetectorUnitTest(unittest.TestCase):
    """Unit tests for the I6 non-canonical-value detectors. Without
    these, a regression in a sub-detector would silently pass the
    integration test (which only asserts "no offenders" on the real
    code).
    """

    def test_repr_call_caught(self) -> None:
        tree = ast.parse('stable_fingerprint({"value": repr(x)})')
        call = tree.body[0].value
        self.assertEqual(_non_canonical_kinds(call.args[0]), ["repr(...)"])

    def test_fstring_repr_conversion_caught(self) -> None:
        tree = ast.parse('stable_fingerprint({"value": f"{x!r}"})')
        call = tree.body[0].value
        self.assertIn('f"{x!r}"', _non_canonical_kinds(call.args[0]))

    def test_fstring_no_conversion_not_caught(self) -> None:
        # Plain f-string interpolation (no !r) is canonical-passing —
        # the value is interpolated by Python's normal __format__.
        tree = ast.parse('stable_fingerprint({"value": f"{x}"})')
        call = tree.body[0].value
        kinds = _non_canonical_kinds(call.args[0])
        self.assertNotIn('f"{x!r}"', kinds)

    def test_format_call_caught(self) -> None:
        tree = ast.parse('stable_fingerprint({"value": format(x, "f")})')
        call = tree.body[0].value
        self.assertIn("format(x, ...)", _non_canonical_kinds(call.args[0]))

    def test_str_of_normalize_caught(self) -> None:
        tree = ast.parse('stable_fingerprint({"value": str(x.normalize())})')
        call = tree.body[0].value
        self.assertIn(
            "str(x.normalize())", _non_canonical_kinds(call.args[0])
        )

    def test_canonical_value_pass_through_not_caught(self) -> None:
        tree = ast.parse('stable_fingerprint({"value": x})')
        call = tree.body[0].value
        self.assertEqual(_non_canonical_kinds(call.args[0]), [])


if __name__ == "__main__":
    unittest.main()
