"""Invariant I5: no Decimal arithmetic on rule outputs outside the rule graph.

Engine principle (CLAUDE.md, ``docs/invariant-migration-plan.md`` section 3):
all legal math lives inside ``LawRule.calculate`` bodies. Pipeline orchestrator
scripts and renderer projections are I/O glue -- they marshal facts into the
rule graph, read rule outputs back out, and lay them onto forms or JSON. They
must NOT add, subtract, multiply, or divide rule-output values, because every
such operation escapes the audit graph (no ``StageResult`` fingerprint, no
``OutputDeclaration``, no statute citation).

This test AST-scans every Pipeline 2 module under
``tax_pipeline/pipelines/y2025/`` (excluding ``__init__.py`` and
``run_derivation.py``, which is Pipeline 1) and flags every ``BinOp``
(``+ - * / // %``) where either operand is a rule-output read or a value
transitively derived from one. F-A6 (architecture review,
``.review/2026-05-01-final/architecture.md``) expanded the scan from the
original three orchestrator/projection modules to the full Pipeline 2
surface so audit-packet writers, narrative packet builders, treaty
workpapers, and renderer entry sheets can no longer hide ad-hoc legal
math behind a "this isn't a rule body" technicality.

To allow a deliberate non-legal computation (e.g., shaping a narrative
string, aggregating already-fingerprinted display values for a CSV
column), append a trailing comment ``# pragma: legal-math-ok <reason>``
on the offending line. Reasons must cite the controlling §-authority or
explain why the math is display-only and pre-graph (loaders that
aggregate raw inputs before the rule graph reads them are pre-graph and
qualify).

Authority: CLAUDE.md ("Tax-Law Rule Requirements") -- renderers must not
perform legal math; final legal-core outputs are display-only at the
orchestrator boundary. Per invariant migration plan section 3 / WS-5.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "tax_pipeline" / "pipelines" / "y2025"

# F-A6: scan every Pipeline 2 module under ``tax_pipeline/pipelines/y2025/``.
# ``__init__.py`` is the package marker (no math) and ``run_derivation.py``
# is Pipeline 1, not Pipeline 2 -- both are excluded by name. Auto-discover
# the remaining files via glob so adding a new Pipeline 2 module is
# automatically scanned.
EXCLUDED_FILE_NAMES = frozenset({"__init__.py", "run_derivation.py"})


def _discover_scanned_files() -> tuple[Path, ...]:
    if not PIPELINE_DIR.exists():
        return ()
    return tuple(
        sorted(
            p
            for p in PIPELINE_DIR.glob("*.py")
            if p.name not in EXCLUDED_FILE_NAMES
        )
    )


SCANNED_FILES = _discover_scanned_files()

# Receiver names whose attributes are rule-output reads. e.g.
# ``capital.foreign_tax_credit_eur``, ``assessment.ftc.total_allowed_ftc_usd``.
RULE_OUTPUT_RECEIVER_NAMES = frozenset(
    {
        "assessment",
        "bridge",
        "bridge_result",
        "capital",
        "final",
        "ordinary",
        "result",
        "treaty",
        "vanilla_checkpoint",
    }
)

# Subscript receivers that hold a fact mapping. ``inputs["foreign_tax_1099_eur"]``
# reads a declared input fact; treat as rule-output-like. The
# ``tax_estimate`` / ``us_tax_estimate`` / ``de_tax_estimate`` / ``forms``
# entries close the long-standing blind spot that the B2 audit pass
# uncovered: ``ftc = tax_estimate["ftc"]`` is a dict-typed local pulled
# from the projected final-legal-output, and Decimal arithmetic on its
# values escaped the receiver-name heuristic because ``ftc`` /
# ``treaty`` / ``capital`` (the dict-typed sub-locals) were the only
# names tracked, not the parent ``tax_estimate``. Adding the parent
# names here taints any sub-local pulled from them via subscript /
# ``.get(...)``, so the I5 detector now flags ``ftc[allowed_general] +
# ftc[allowed_passive]``-style smells at the projection boundary.
FACT_MAPPING_RECEIVER_NAMES = frozenset(
    {
        "inputs",
        "facts",
        "ordinary_inputs",
        "capital_inputs",
        # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — tax_estimate /
        # us_tax_estimate / de_tax_estimate / forms are the projected
        # rule-output mappings produced by ``us_model.build_us_models``
        # / ``germany_model.build_germany_models`` and read by every
        # treaty-packet / verbose-report / narrative-packet writer.
        "tax_estimate",
        "us_tax_estimate",
        "de_tax_estimate",
        "forms",
        "usa_forms",
        "germany_forms",
    }
)

# Subscript-key namespace prefixes that mark a rule-output read regardless of
# the receiver, e.g. ``ctx["de.capital.foreign_tax_credit_eur"]``.
RULE_OUTPUT_KEY_PREFIXES = ("de.", "us.", "treaty.", "bridge.")

LEGAL_MATH_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)

ALLOWLIST_PRAGMA = "pragma: legal-math-ok"

# Variable-name prefixes that connote a rule-graph value. A local
# assignment ``tax_xyz = a + b`` (or ``legal_…``, ``refund_…``,
# ``schedule_…``, ``form_…``, ``line_…``) is strong evidence the
# variable holds a legally meaningful number, even if neither operand
# is itself recognised as a rule-output read. This catches the failure
# mode where a renderer computes a "tax owed" / "schedule_3_line_1" /
# "form_1040_line_22" from raw facts before laying it on a form.
#
# B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — added the form-line
# prefixes (``schedule_``, ``form_``, ``line_``) because the bypass
# pattern that B2 closed at ``us_treaty_packet.py:147`` had an LHS
# ``schedule3_line1`` (no leading underscore separator), and the prior
# heuristic only recognised ``legal_`` / ``tax_`` / ``refund_``.
LEGAL_NAME_PREFIXES = (
    "legal_",
    "tax_",
    "refund_",
)

# Pattern-based check for form-line LHS names. Matches:
#   - schedule<digits|letters>_line<num>...
#   - schedule_line<num>...
#   - form<digits>_line<num>...
#   - form_line<num>...
#   - line<num>...
#   - line_<num>...
# The pattern is intentionally permissive so naming conventions like
# ``schedule3_line1`` (no underscore between "schedule" and "3") and
# ``form_1040_line_22`` (extra underscores) are both flagged.
_FORM_LINE_NAME_RE = re.compile(
    r"^(legal|tax|refund|schedule[a-z0-9]*|form[0-9]*|line)_?(line)?_?[0-9a-z]"
)


def _is_legal_named_lhs(name: str) -> bool:
    if name.startswith(LEGAL_NAME_PREFIXES):
        return True
    return bool(_FORM_LINE_NAME_RE.match(name))


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_rule_output_read(node: ast.AST) -> bool:
    """True iff ``node`` directly reads a value produced by the rule graph."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id in RULE_OUTPUT_RECEIVER_NAMES
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
        return _is_rule_output_read(node.value)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id in FACT_MAPPING_RECEIVER_NAMES:
            return True
        key = _const_str(node.slice)
        if key is not None and key.startswith(RULE_OUTPUT_KEY_PREFIXES):
            return True
    return False


class _TaintTracker(ast.NodeVisitor):
    """Per-function flow-insensitive taint analysis.

    Marks local names as tainted when they receive a value derived from a
    rule-output read. Function parameters are seeded as tainted if their name
    suggests a rule-output (``inputs``, ``capital``, ``assessment``,
    ``*_facts``, ``*_eur``, ``*_usd``) -- this catches projection helpers
    whose body accumulates Decimals from those arguments.
    """

    def __init__(self, func: ast.FunctionDef) -> None:
        self.tainted: set[str] = set()
        self.offenders: list[tuple[int, str]] = []
        for arg in (*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs):
            name = arg.arg
            if (
                name in RULE_OUTPUT_RECEIVER_NAMES
                or name in FACT_MAPPING_RECEIVER_NAMES
                or name.endswith(("_eur", "_usd", "_facts", "_inputs", "_assessment"))
            ):
                self.tainted.add(name)
        for stmt in func.body:
            self.visit(stmt)

    def _expr_is_tainted(self, node: ast.AST) -> bool:
        if _is_rule_output_read(node):
            return True
        if isinstance(node, ast.Name):
            return node.id in self.tainted or node.id in FACT_MAPPING_RECEIVER_NAMES
        if isinstance(node, ast.Attribute):
            return self._expr_is_tainted(node.value)
        if isinstance(node, ast.Subscript):
            return self._expr_is_tainted(node.value) or _is_rule_output_read(node)
        if isinstance(node, ast.BinOp):
            return self._expr_is_tainted(node.left) or self._expr_is_tainted(node.right)
        if isinstance(node, ast.UnaryOp):
            return self._expr_is_tainted(node.operand)
        if isinstance(node, ast.Call):
            # ``D(fact.eur_amount)``, ``q2(x)``, ``min(a, b)``,
            # ``sum((... for ... in tainted), D("0.00"))``, and ALSO
            # ``tax_estimate.get("ftc", {})`` / ``forms.get(...)`` etc.
            # — propagate taint from the call's receiver so dict-typed
            # locals pulled from ``FACT_MAPPING_RECEIVER_NAMES`` via
            # ``.get(...)`` are tainted, closing the blind spot that
            # the B2 audit pass uncovered.
            if self._expr_is_tainted(node.func):
                return True
            return any(self._expr_is_tainted(a) for a in node.args) or any(
                self._expr_is_tainted(kw.value) for kw in node.keywords
            )
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return any(self._expr_is_tainted(elt) for elt in node.elts)
        if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            if self._expr_is_tainted(node.elt):
                return True
            return any(self._expr_is_tainted(gen.iter) for gen in node.generators)
        if isinstance(node, ast.IfExp):
            return self._expr_is_tainted(node.body) or self._expr_is_tainted(node.orelse)
        return False

    def _mark_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.tainted.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._mark_target(elt)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._expr_is_tainted(node.value):
            for target in node.targets:
                self._mark_target(target)
        # Heuristic: a local var named ``legal_*`` / ``tax_*`` / ``refund_*``
        # that is assigned a Decimal BinOp is by name a legal-math LHS
        # even if neither operand is independently tainted (e.g.,
        # ``tax_owed = D("100") + D("50")``). Flag it; mark the target
        # tainted for downstream propagation.
        if isinstance(node.value, ast.BinOp) and isinstance(node.value.op, LEGAL_MATH_OPS):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and _is_legal_named_lhs(target.id)
                ):
                    try:
                        snippet = ast.unparse(node)
                    except Exception:  # pragma: no cover - defensive
                        snippet = "<unparse-failed>"
                    self.offenders.append((node.lineno, snippet))
                    self.tainted.add(target.id)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._expr_is_tainted(node.value):
            self._mark_target(node.target)
        self._check_binop(node, node.target, node.value)
        # Heuristic: ``tax_xyz += amount`` on a legal-named var counts.
        if (
            isinstance(node.target, ast.Name)
            and _is_legal_named_lhs(node.target.id)
            and isinstance(node.op, LEGAL_MATH_OPS)
        ):
            try:
                snippet = ast.unparse(node)
            except Exception:  # pragma: no cover - defensive
                snippet = "<unparse-failed>"
            self.offenders.append((node.lineno, snippet))
            self.tainted.add(node.target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and self._expr_is_tainted(node.value):
            self._mark_target(node.target)
        if (
            node.value is not None
            and isinstance(node.value, ast.BinOp)
            and isinstance(node.value.op, LEGAL_MATH_OPS)
            and isinstance(node.target, ast.Name)
            and _is_legal_named_lhs(node.target.id)
        ):
            try:
                snippet = ast.unparse(node)
            except Exception:  # pragma: no cover - defensive
                snippet = "<unparse-failed>"
            self.offenders.append((node.lineno, snippet))
            self.tainted.add(node.target.id)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        if self._expr_is_tainted(node.iter):
            self._mark_target(node.target)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self._check_binop(node, node.left, node.right)
        self.generic_visit(node)

    def _check_binop(self, node: ast.AST, left: ast.AST, right: ast.AST) -> None:
        op = getattr(node, "op", None)
        if not isinstance(op, LEGAL_MATH_OPS):
            return
        if not (self._expr_is_tainted(left) or self._expr_is_tainted(right)):
            return
        try:
            snippet = ast.unparse(node)
        except Exception:  # pragma: no cover - defensive
            snippet = "<unparse-failed>"
        self.offenders.append((node.lineno, snippet))


def _allowlisted_lines(source: str) -> set[int]:
    return {
        i
        for i, line in enumerate(source.splitlines(), start=1)
        if ALLOWLIST_PRAGMA in line
    }


def _scan_file(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = _allowlisted_lines(source)
    rel = path.relative_to(REPO_ROOT)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_TaintTracker(node).offenders)
    seen: set[tuple[int, str]] = set()
    out: list[str] = []
    for lineno, snippet in sorted(findings):
        if lineno in allowed or (lineno, snippet) in seen:
            continue
        seen.add((lineno, snippet))
        out.append(f"{rel}:{lineno}: {snippet[:160]}")
    return out


class NoLegalMathOutsideRuleGraphTest(unittest.TestCase):
    """Per CLAUDE.md -- "Renderers must not perform legal math. They may only
    display final legal-core outputs and cited trace/narrative metadata."

    F-A6 expanded the scan from orchestrator/projection modules only to
    every Pipeline 2 module (audit-packet writers, narrative packet
    builders, treaty workpapers, ELSTER entry sheets, vanilla
    checkpoints, verbose reports, etc.). Pipeline 2 modules translate
    rule outputs into display/audit artifacts and must never compute new
    legal numbers; legitimate pre-graph aggregation in loaders carries a
    `# pragma: legal-math-ok` with a § citation explaining why the math
    runs before the rule graph reads its inputs.
    """

    def test_no_decimal_arithmetic_on_rule_outputs_in_orchestrators(self) -> None:
        offenders: list[str] = []
        for path in SCANNED_FILES:
            self.assertTrue(path.exists(), f"missing scanned file: {path}")
            offenders.extend(_scan_file(path))
        self.assertEqual(
            offenders,
            [],
            "Found Decimal arithmetic on rule-output values outside the rule "
            "graph. Promote each computation to a LawRule.calculate body "
            "(e.g., a new BRIDGE25-* or DE25-*-FINAL-* stage with proper "
            "OutputDeclaration and FormLineRef) so the result is fingerprinted "
            "and cited. If the line is genuinely non-legal display arithmetic, "
            "append `# pragma: legal-math-ok <reason>`. Offenders:\n  - "
            + "\n  - ".join(offenders),
        )


class LegalNamedLHSDetectorTest(unittest.TestCase):
    """Unit tests for the LHS-by-name heuristic. Without these, a
    regression in the visitor itself would silently pass the
    integration test (which only asserts "no offenders" on real
    Pipeline 2 files).
    """

    def _scan(self, snippet: str) -> list[str]:
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

    def test_tax_named_lhs_with_binop_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    tax_owed = Decimal("100") + Decimal("50")\n'
            '    return tax_owed\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_legal_named_lhs_with_binop_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    legal_total = Decimal("1") - Decimal("0.5")\n'
            '    return legal_total\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_refund_named_lhs_with_binop_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    refund_amount = Decimal("100") * Decimal("0.05")\n'
            '    return refund_amount\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_unrelated_named_lhs_with_binop_not_caught(self) -> None:
        # A bare ``x = D("1") + D("2")`` with an untainted RHS is NOT
        # flagged — the heuristic intentionally only fires for
        # legal/tax/refund-named LHS.
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    x = Decimal("1") + Decimal("2")\n'
            '    return x\n'
        )
        self.assertEqual(offenders, [])

    def test_legal_named_aug_assign_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    tax_owed = Decimal("0")\n'
            '    tax_owed += Decimal("100")\n'
            '    return tax_owed\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_legal_named_lhs_pragma_suppresses(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    tax_owed = Decimal("100") + Decimal("50")  # pragma: legal-math-ok display total\n'
            '    return tax_owed\n'
        )
        self.assertEqual(offenders, [])

    # ---- B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) -------------------
    # Two new heuristics close the long-standing blind spots that the
    # B2 audit pass uncovered at ``us_treaty_packet.py:147``:
    #   (a) tax_estimate-receiver subscripts — dict-typed locals pulled
    #       from ``tax_estimate["ftc"]`` (or ``.get("ftc", {})``) are
    #       tainted, so ``ftc[allowed_general] + ftc[allowed_passive]``
    #       at the projection boundary is now flagged.
    #   (b) form-line LHS prefixes — ``schedule_*`` / ``form_*`` /
    #       ``line_*`` names join the ``legal_`` / ``tax_`` / ``refund_``
    #       trio so a renderer that builds a ``schedule3_line1`` /
    #       ``form_1040_line_22`` from raw Decimals is flagged.

    def test_tax_estimate_subscript_taint_propagates(self) -> None:
        offenders = self._scan(
            'def render(tax_estimate):\n'
            '    ftc = tax_estimate["ftc"]\n'
            '    total = ftc["allowed_general_ftc_usd"] + ftc["allowed_passive_ftc_usd"]\n'
            '    return total\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_tax_estimate_get_taint_propagates(self) -> None:
        offenders = self._scan(
            'def render(tax_estimate):\n'
            '    ftc = tax_estimate.get("ftc", {})\n'
            '    total = ftc["allowed_general_ftc_usd"] + ftc["allowed_passive_ftc_usd"]\n'
            '    return total\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_us_tax_estimate_subscript_taint_propagates(self) -> None:
        # ``us_tax_estimate`` is the orchestrator-side argument name.
        offenders = self._scan(
            'def render(us_tax_estimate):\n'
            '    capital = us_tax_estimate["capital"]\n'
            '    sum_eur = capital["short_box_h_usd"] + capital["long_box_k_usd"]\n'
            '    return sum_eur\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_schedule_named_lhs_with_binop_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    schedule3_line1 = Decimal("100") + Decimal("50")\n'
            '    return schedule3_line1\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_form_named_lhs_with_binop_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    form_1040_line_22 = Decimal("1000") - Decimal("123")\n'
            '    return form_1040_line_22\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_line_named_lhs_with_binop_caught(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    line_23_total = Decimal("1") + Decimal("2")\n'
            '    return line_23_total\n'
        )
        self.assertTrue(offenders, f"got: {offenders}")

    def test_form_named_pragma_suppresses(self) -> None:
        offenders = self._scan(
            'from decimal import Decimal\n'
            'def render():\n'
            '    form_1040_line_22 = Decimal("1") + Decimal("2")  # pragma: legal-math-ok display total\n'
            '    return form_1040_line_22\n'
        )
        self.assertEqual(offenders, [])


class ScannedFilesAutodiscoveryTest(unittest.TestCase):
    """Auto-discovery of SCANNED_FILES must include every existing
    Pipeline 2 module, and must continue to exclude the package marker
    and the Pipeline 1 ``run_derivation`` script.
    """

    def test_all_y2025_modules_discovered_except_excluded(self) -> None:
        actual_names = {p.name for p in PIPELINE_DIR.glob("*.py")}
        scanned_names = {p.name for p in SCANNED_FILES}
        # Every .py under Pipeline 2 except the explicit excludes.
        self.assertEqual(scanned_names, actual_names - EXCLUDED_FILE_NAMES)
        for excluded in EXCLUDED_FILE_NAMES:
            self.assertNotIn(excluded, scanned_names)


if __name__ == "__main__":
    unittest.main()
