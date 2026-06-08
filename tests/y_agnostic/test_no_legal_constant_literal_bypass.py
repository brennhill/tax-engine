"""Invariant I1 — no legal-constant literal bypass.

A ``Decimal("X")`` / ``D("X")`` literal whose numeric value matches a
named constant declared at module scope in one of the three 2025 law
modules (``y2025/germany_law.py``, ``y2025/us_law.py``,
``y2025/treaty_law.py``) MUST import the named constant rather than
re-typing the literal. The literal also MUST NOT be smuggled inside
``Decimal(str(row.get(key, "X")))`` row defaults — every string literal
passed to a Decimal/D constructor counts.

Authority and rationale
-----------------------
- DBA-USA Art. 10(2)(b) — 15% source-state cap on portfolio dividends.
  https://www.irs.gov/pub/irs-trty/germany.pdf
  Single canonical declaration:
  ``DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE`` in
  ``tax_pipeline/y2025/treaty_law.py``.
- Solidaritaetszuschlaggesetz § 4 — 5.5% solidarity surcharge.
  https://www.gesetze-im-internet.de/solzg_1995/__4.html
  Single canonical declaration: ``SOLI_RATE`` in
  ``tax_pipeline/y2025/germany_law.py``.
- § 32d Abs. 1 Satz 1 EStG — 25% Abgeltungsteuer rate.
  https://www.gesetze-im-internet.de/estg/__32d.html
  Single canonical declaration: ``CAPITAL_TAX_RATE_2025`` in
  ``tax_pipeline/y2025/germany_law.py``.
- § 20 Abs. 9 Sätze 1 und 2 EStG — €1,000 / €2,000 Sparer-Pauschbetrag.
  https://www.gesetze-im-internet.de/estg/__20.html
  Single canonical declarations: ``SAVER_ALLOWANCE_SINGLE_2025_EUR`` and
  ``SAVER_ALLOWANCE_JOINT_2025_EUR`` in
  ``tax_pipeline/y2025/germany_law.py``.
- § 22 Nr. 3 Satz 2 EStG — €256 Freigrenze on sonstige Einkünfte.
  https://www.gesetze-im-internet.de/estg/__22.html
  Single canonical declaration:
  ``OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR`` in
  ``tax_pipeline/y2025/germany_law.py``.
- IRC § 1411 — 3.8% Net Investment Income Tax.
  https://www.law.cornell.edu/uscode/text/26/1411
- IRC § 1(h)(1)(C) — qualified-dividend / LTCG 15% bracket.
  https://www.law.cornell.edu/uscode/text/26/1

A literal that drifts from the named constant is the class of bug that
produces silent legal incorrectness (e.g., a treaty protocol amendment
changes 15% to 10% but a hidden ``"0.15"`` row default keeps the old
rate). Per project CLAUDE.md, tax-rule constants must cite the
controlling legal authority and live behind a single named declaration.
The ``ALLOWED_LITERAL_OCCURRENCES`` allowlist mirrors
``ALLOWED_NON_TREATY_DECIMAL_0_15_OCCURRENCES`` in
``tests/test_y2025/treaty_law.py``: each entry forces an explicit
affirmation that an unrelated statute happens to share the same number.
"""
from __future__ import annotations

import ast
import tomllib
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PIPELINE_DIR = REPO_ROOT / "tax_pipeline"
LAW_TREE_DIR = REPO_ROOT / "law"
LAW_MODULE_PATHS = tuple(
    (TAX_PIPELINE_DIR / "y2025" / name).resolve()
    for name in ("germany_law.py", "us_law.py", "treaty_law.py")
)


def _law_tree_per_statute_paths() -> tuple[Path, ...]:
    """Per-statute canonical files under ``law/`` — each pXX.py / artNN.py
    file is its own canonical declaration site. Test files and ``__init__``
    markers are excluded.
    """
    if not LAW_TREE_DIR.exists():
        return ()
    out: list[Path] = []
    for py_file in LAW_TREE_DIR.rglob("*.py"):
        name = py_file.name
        if name.endswith("_test.py") or name == "__init__.py":
            continue
        out.append(py_file.resolve())
    return tuple(out)


LAW_TREE_PATHS = _law_tree_per_statute_paths()

# Allowlist: resolved path -> set of source-line substrings. A flagged
# literal whose source line contains any allowed substring is permitted
# because the value comes from an unrelated statute that happens to
# share the number. Add an entry only with a citation comment in the
# source file proving the use is from a distinct legal authority.
ALLOWED_LITERAL_OCCURRENCES: dict[Path, set[str]] = {
    # § 20 InvStG (Investmentsteuergesetz) Teilfreistellung rate of 30 %
    # for Aktienfonds (https://www.gesetze-im-internet.de/invstg_2018/__20.html)
    # numerically coincides with the 30 %-of-FEIE statutory housing-cost
    # ceiling under 26 U.S.C. § 911(c)(2)(A) (Workstream 1) but is a
    # distinct legal authority from a different jurisdiction's investment
    # fund regime. The InvStG rate is declared in
    # ``y2025/derive_treaty_dividend_items.py`` near the per-fund-class
    # treaty derivation it controls.
    (REPO_ROOT / "tax_pipeline" / "y2025" / "derive_treaty_dividend_items.py").resolve(): {
        "TEILFREISTELLUNG_RATE_AKTIENFONDS",
    },
}

# Trivial Decimal sentinels universally needed in any currency code
# (zero, one cent). They are NOT legal-rate / legal-threshold constants
# whose drift would mis-state the law: a stray ``Decimal("0.00")`` is
# structurally indistinguishable from any other zero. Constants whose
# name starts ``ZERO_`` or ends ``_CENT`` are out-of-scope so the test's
# signal stays on legal rates and statutory amounts.
_SENTINEL_PREFIXES = ("ZERO_",)
_SENTINEL_SUFFIXES = ("_CENT",)


def _is_sentinel(name: str) -> bool:
    return name.startswith(_SENTINEL_PREFIXES) or name.endswith(_SENTINEL_SUFFIXES)


def _law_constants(path: Path) -> dict[Decimal, str]:
    """Top-level ``NAME = Decimal("X")`` / ``D("X")`` assignments from a
    law module, as ``{Decimal_value: name}``. Sentinels are excluded.

    Also picks up Decimal/D values appearing inside top-level dict-literal
    assignments (e.g., ``FUND_TEILFREISTELLUNG_RATES_2025 = {"aktien": D("0.30"),
    ...}``) so the canonical-rate map for InvStG § 20 etc. registers as
    canonical for its own file.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[Decimal, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target_node = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target_node = node.target
            value = node.value
        else:
            continue
        if not isinstance(target_node, ast.Name) or _is_sentinel(target_node.id):
            continue
        target = target_node
        # Direct ``NAME = Decimal("X")`` form.
        if isinstance(value, ast.Call):
            func = value.func
            if (
                isinstance(func, ast.Name)
                and func.id in ("Decimal", "D")
                and value.args
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                try:
                    out.setdefault(Decimal(value.args[0].value), target.id)
                except InvalidOperation:
                    pass
                continue
        # Note: dict-table / tuple values (e.g., ZUMUTBARE_BELASTUNG_2025_RATES,
        # ALTERSENTLASTUNGSBETRAG_2025_TABLE) are deliberately NOT extracted as
        # named canonicals here — many of those values are tiny percentages
        # (0.01, 0.02, 0.04 ...) that coincide with display-rounding cent
        # values across the codebase and would generate noise. The per-file
        # ``_file_decimal_literals`` pass below ensures the canonical's own
        # file is still excluded from the cross-file detector.
    return out


def _file_decimal_literals(path: Path) -> set[Decimal]:
    """Every literal-string ``Decimal(...)`` / ``D(...)`` value that
    appears anywhere in ``path``'s source. Used to compute the per-file
    canonical set: the per-statute file is canonical for every Decimal
    rate it embeds (top-level singleton constants, dict-table values,
    tuple values), so we must skip flags inside its own body for any
    of those values.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    out: set[Decimal] = set()
    for sub in ast.walk(tree):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if not (isinstance(func, ast.Name) and func.id in ("Decimal", "D")):
            continue
        if not sub.args or not isinstance(sub.args[0], ast.Constant):
            continue
        arg = sub.args[0].value
        if not isinstance(arg, str):
            continue
        try:
            out.add(Decimal(arg))
        except InvalidOperation:
            continue
    return out


def _law_toml_constants(path: Path) -> dict[Decimal, str]:
    """Statutory constants declared in a ``law/<...>/p<§>.toml`` data file
    as ``{Decimal_value: NAME}``.

    Per New-1 (2026-05-10 platform-flexibility review) the F1 shadow
    TOMLs are the single source of truth for the 78 working-tree
    statutory constants. After the working-tree migration replaces
    ``NAME = Decimal("X")`` with ``NAME = _LAW_DATA["NAME"]``, the
    only Python-AST canonical-declaration site is gone — the canonical
    now lives in the TOML. This helper walks the TOML so the I1
    cross-file detector retains coverage.

    Sentinels (``ZERO_*`` / ``*_CENT``) are excluded for the same
    reason as :func:`_law_constants`.
    """
    out: dict[Decimal, str] = {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return out
    for name, entry in data.items():
        if _is_sentinel(name):
            continue
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if not isinstance(value, str):
            continue
        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            continue
        out.setdefault(decimal_value, name)
    return out


def _law_tree_per_statute_toml_paths() -> tuple[Path, ...]:
    """Every ``p<§>.toml`` / ``art<NN>.toml`` data file under ``law/``."""
    if not LAW_TREE_DIR.exists():
        return ()
    return tuple(p.resolve() for p in LAW_TREE_DIR.rglob("*.toml"))


LAW_TREE_TOML_PATHS = _law_tree_per_statute_toml_paths()


def _build_index() -> dict[Decimal, list[tuple[str, str]]]:
    """Build ``{value: [(canonical_file_label, name), ...]}`` from every
    canonical declaration site — the three ``tax_pipeline/*_2025_law.py``
    modules, every per-statute Python file under ``law/``, and every
    sibling TOML data file under ``law/``.

    Per New-1 the working-tree law modules read constants from the F1
    TOMLs via :data:`tax_pipeline._law_data.LAW_DATA`, so the TOML is
    the structural canonical-declaration site. Including the TOML
    walk here means an offending ``Decimal("X")`` literal is still
    flagged when ``X`` matches a TOML-declared statutory value, even
    though the working-tree law module no longer carries the literal.

    Decimal zero is excluded by construction. A constant whose canonical
    value is 0 (e.g., DBA-USA Art. 11 source-state interest rate is
    0% by treaty) is structurally indistinguishable from a generic zero
    literal (``Decimal("0.00")`` initialiser) and would produce noise.
    Same posture as the ``ZERO_*`` sentinel exclusion.
    """
    index: dict[Decimal, list[tuple[str, str]]] = {}

    def _record(label: str, value: Decimal, name: str) -> None:
        if value == 0:
            return
        index.setdefault(value, []).append((label, name))

    for path in LAW_MODULE_PATHS:
        for value, name in _law_constants(path).items():
            _record(path.name, value, name)
    for path in LAW_TREE_PATHS:
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:  # pragma: no cover - defensive
            rel = path.name
        for value, name in _law_constants(path).items():
            _record(rel, value, name)
    for toml_path in LAW_TREE_TOML_PATHS:
        try:
            rel = str(toml_path.relative_to(REPO_ROOT))
        except ValueError:  # pragma: no cover - defensive
            rel = toml_path.name
        for value, name in _law_toml_constants(toml_path).items():
            _record(rel, value, name)
    return index


def _decimal_value_from_call(node: ast.Call) -> Decimal | None:
    """Return the Decimal numeric value of a ``Decimal(...)`` / ``D(...)``
    call when the argument is a single literal constant.

    Recognised forms:
      - ``Decimal("0.15")`` — the canonical string form.
      - ``Decimal("0.150")`` — same numeric value, trailing zeros normalised.
      - ``Decimal(0.15)`` — float argument (constructor will internally convert).
      - ``Decimal(15)`` — integer argument.

    Returns None if the call is not a single-literal Decimal/D call.
    """
    func = node.func
    if not (isinstance(func, ast.Name) and func.id in ("Decimal", "D")):
        return None
    if len(node.args) != 1 or node.keywords:
        return None
    arg = node.args[0]
    if not isinstance(arg, ast.Constant):
        return None
    try:
        if isinstance(arg.value, str):
            return Decimal(arg.value)
        if isinstance(arg.value, int):
            return Decimal(arg.value)
        if isinstance(arg.value, float):
            # ``Decimal(0.15)`` is a misuse — the float double-conversion
            # produces a Decimal with the float's binary remainder. We
            # use str(float) to recover the legally intended value, which
            # is exactly the bug class this rule catches.
            return Decimal(str(arg.value))
    except InvalidOperation:
        return None
    return None


def _binop_division_decimal_value(node: ast.BinOp) -> Decimal | None:
    """Return the numeric value of ``Decimal("X") / Decimal("Y")`` (or
    ``D(...)/ D(...)``) where both sides are single-literal Decimal calls.

    This catches the pattern ``Decimal("15") / Decimal("100")`` that
    bypasses a literal "0.15" check by hiding the rate behind a
    division. Result is normalised to a Decimal so it compares equal
    to a canonical ``Decimal("0.15")`` law constant.
    """
    if not isinstance(node.op, ast.Div):
        return None
    if not (isinstance(node.left, ast.Call) and isinstance(node.right, ast.Call)):
        return None
    left = _decimal_value_from_call(node.left)
    right = _decimal_value_from_call(node.right)
    if left is None or right is None:
        return None
    if right == 0:
        return None
    try:
        return left / right
    except (InvalidOperation, ZeroDivisionError):
        return None


def _iter_literal_calls(tree: ast.AST):
    """Yield ``(node, value)`` pairs for every literal expression whose
    numeric value is a Decimal that could match a law constant.

    Catches:
      - ``Decimal("0.15")`` / ``D("0.15")`` (canonical string form)
      - ``Decimal("0.150")`` (trailing-zero variant)
      - ``Decimal(0.15)`` (float-arg misuse)
      - ``Decimal(15)`` (int-arg)
      - ``Decimal("15") / Decimal("100")`` (division pattern)
      - smuggled ``Decimal(str(row.get("rate", "0.15")))`` (string descendant)

    The first item of each yielded tuple is the AST node carrying the
    diagnostic line number; the second is the canonical Decimal value
    used to match against the law-constant index.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            value = _binop_division_decimal_value(node)
            if value is not None:
                yield node, value
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("Decimal", "D")):
            continue
        # Direct single-literal form (string / float / int).
        direct = _decimal_value_from_call(node)
        if direct is not None:
            yield node, direct
            continue
        # Smuggled form: any string-Constant descendant of the args.
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    try:
                        yield node, Decimal(sub.value)
                    except InvalidOperation:
                        continue


class NoLegalConstantLiteralBypassTest(unittest.TestCase):
    """I1 — Reject Decimal/D literals outside the law modules whose numeric
    value duplicates a named constant from one of the 2025 law modules.
    """

    maxDiff = None

    def test_no_law_constant_literal_outside_law_modules(self) -> None:
        law_constants = _build_index()
        self.assertIn(
            Decimal("0.15"), law_constants,
            "tax_pipeline/y2025/treaty_law.py must declare the canonical 15% rate",
        )
        # F-DE-1: the four formerly CSV-only Germany statutory constants
        # plus the existing 5.5% solidarity-surcharge rate must be canonical
        # in y2025/germany_law.py so the auto-detector forbids any literal of
        # those numeric values elsewhere in tax_pipeline/.
        self.assertIn(
            Decimal("0.25"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 25% Abgeltungsteuer "
            "rate (CAPITAL_TAX_RATE_2025, § 32d Abs. 1 Satz 1 EStG)",
        )
        self.assertIn(
            Decimal("2000.00"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical joint Sparer-"
            "Pauschbetrag (SAVER_ALLOWANCE_JOINT_2025_EUR, § 20 Abs. 9 EStG)",
        )
        self.assertIn(
            Decimal("1000.00"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical single Sparer-"
            "Pauschbetrag (SAVER_ALLOWANCE_SINGLE_2025_EUR, § 20 Abs. 9 EStG)",
        )
        self.assertIn(
            Decimal("256.00"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical § 22 Nr. 3 Satz 2 "
            "Freigrenze (OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR)",
        )
        self.assertIn(
            Decimal("0.055"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 5.5% Solidaritäts-"
            "zuschlag rate (SOLI_RATE, § 4 SolzG 1995)",
        )
        # Wave 11A — § 31 EStG / § 32 Abs. 6 EStG / BKGG canonical constants for
        # the German Familienleistungsausgleich. The Kinderfreibetrag (€6,672),
        # BEA-Freibetrag (€2,928), combined Freibetrag (€9,600), monthly
        # Kindergeld (€250), and annual Kindergeld (€3,000) are statutory
        # rates/amounts that must remain canonical in y2025/germany_law.py so a
        # rate revision (Steuerfortentwicklungsgesetz / BKGG amendment) is a
        # single edit point.
        self.assertIn(
            Decimal("6672"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 2025 "
            "Kinderfreibetrag (KINDERFREIBETRAG_2025_EUR, § 32 Abs. 6 Satz 1 EStG)",
        )
        self.assertIn(
            Decimal("2928"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 2025 BEA-"
            "Freibetrag (BEA_FREIBETRAG_2025_EUR, § 32 Abs. 6 Satz 2 EStG)",
        )
        self.assertIn(
            Decimal("9600"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 2025 combined "
            "Kinderfreibetrag (COMBINED_KINDERFREIBETRAG_2025_EUR, § 32 Abs. 6 EStG)",
        )
        self.assertIn(
            Decimal("255"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 2025 monthly "
            "Kindergeld (KINDERGELD_2025_MONTHLY_EUR, BKGG; €255 from "
            "01.01.2025 per Steuerfortentwicklungsgesetz 2024)",
        )
        self.assertIn(
            Decimal("3060"), law_constants,
            "tax_pipeline/y2025/germany_law.py must declare the canonical 2025 annual "
            "Kindergeld (KINDERGELD_2025_ANNUAL_EUR, BKGG)",
        )
        law_paths = {p.resolve() for p in LAW_MODULE_PATHS}
        # Per-statute canonical sites under law/. A given per-statute file
        # is canonical for every Decimal literal it embeds (top-level
        # constants, dict-tables, tuple-tables, helper-body uses of its
        # own canonical rate): skip flags in its own body for any of
        # those values. ``_file_decimal_literals`` walks the entire AST
        # so this covers the dict-table / tuple-of-tuples shapes that
        # ``_law_constants`` deliberately skips for the cross-file index.
        law_tree_canonicals: dict[Path, set[Decimal]] = {}
        for path in LAW_TREE_PATHS:
            law_tree_canonicals[path.resolve()] = _file_decimal_literals(path)
        offenders: list[str] = []
        # Two-pass scan: tax_pipeline/ tree (excluding the three law
        # modules themselves) AND law/ tree (excluding test files and
        # excluding the canonical's own declared values).
        scan_files: list[tuple[Path, frozenset[Decimal]]] = []
        for py_file in TAX_PIPELINE_DIR.rglob("*.py"):
            resolved = py_file.resolve()
            if resolved in law_paths:
                continue
            scan_files.append((py_file, frozenset()))
        for py_file in LAW_TREE_DIR.rglob("*.py"):
            if py_file.name.endswith("_test.py") or py_file.name == "__init__.py":
                continue
            resolved = py_file.resolve()
            scan_files.append(
                (py_file, frozenset(law_tree_canonicals.get(resolved, set())))
            )
        for py_file, own_canonicals in scan_files:
            resolved = py_file.resolve()
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, SyntaxError):
                continue
            source_lines = source.splitlines()
            allowed = ALLOWED_LITERAL_OCCURRENCES.get(resolved, set())
            for offender_node, value in _iter_literal_calls(tree):
                if value in own_canonicals:
                    # Canonical declaration line in its own per-statute
                    # file — by construction the legitimate single edit
                    # point.
                    continue
                matches = law_constants.get(value)
                if not matches:
                    continue
                line_no = offender_node.lineno
                line_text = source_lines[line_no - 1] if 0 < line_no <= len(source_lines) else ""
                if any(s in line_text for s in allowed):
                    continue
                names = ", ".join(f"{m}::{n}" for m, n in matches)
                try:
                    snippet = ast.unparse(offender_node)
                except Exception:  # pragma: no cover - defensive
                    snippet = "<unparse-failed>"
                offenders.append(
                    f"{py_file.relative_to(REPO_ROOT)}:{line_no}: "
                    f"{snippet} == {value} duplicates {names}"
                )
        self.assertEqual(
            offenders, [],
            "Found Decimal/D literals outside the three 2025 law modules "
            "whose numeric value duplicates a named law-module constant. "
            "Use the named constant (import it) instead of retyping the "
            "literal. Add an entry to ALLOWED_LITERAL_OCCURRENCES only "
            "with a citation showing the use is from an unrelated "
            "statute.\nOffenders:\n  " + "\n  ".join(offenders),
        )


class LiteralCallExtractorTest(unittest.TestCase):
    """Unit tests for the AST extractor — proves the new patterns are caught.

    Each test parses a small synthetic snippet, runs ``_iter_literal_calls``,
    and asserts the canonical Decimal value extracted matches the expected
    legal-rate constant. Without these unit tests a regression in the
    extractor itself would silently pass the integration test (the broader
    repo scan only checks "no offenders", which is also true if the
    extractor stops yielding anything).
    """

    def _values(self, snippet: str) -> list[Decimal]:
        tree = ast.parse(snippet)
        return [value for _node, value in _iter_literal_calls(tree)]

    def test_canonical_string_literal_caught(self) -> None:
        # Authority: DBA-USA Art. 10(2)(b) — 15% portfolio dividend cap.
        # https://www.irs.gov/pub/irs-trty/germany.pdf
        self.assertIn(Decimal("0.15"), self._values('Decimal("0.15")'))

    def test_trailing_zero_string_literal_caught(self) -> None:
        # ``Decimal("0.150")`` is numerically identical to the canonical
        # 0.15 rate and must be flagged the same way.
        self.assertIn(Decimal("0.15"), self._values('Decimal("0.150")'))

    def test_float_arg_literal_caught(self) -> None:
        # ``Decimal(0.15)`` is a misuse — float double-conversion. The
        # detector must still recognise the legally intended 15% rate.
        self.assertIn(Decimal("0.15"), self._values('Decimal(0.15)'))

    def test_int_arg_literal_caught(self) -> None:
        self.assertIn(Decimal("256"), self._values('Decimal(256)'))

    def test_division_pattern_caught(self) -> None:
        # ``Decimal("15") / Decimal("100")`` smuggles a 0.15 rate behind
        # an arithmetic expression. Must be caught.
        self.assertIn(
            Decimal("0.15"), self._values('Decimal("15") / Decimal("100")')
        )

    def test_smuggled_string_literal_in_get_default_caught(self) -> None:
        # ``Decimal(str(row.get("rate", "0.15")))`` — original supported
        # form, must remain caught after refactor.
        snippet = 'Decimal(str(row.get("rate", "0.15")))'
        self.assertIn(Decimal("0.15"), self._values(snippet))

    def test_d_alias_works_for_string_form(self) -> None:
        self.assertIn(Decimal("0.15"), self._values('D("0.15")'))

    def test_d_alias_works_for_division_form(self) -> None:
        self.assertIn(Decimal("0.15"), self._values('D("15") / D("100")'))

    def test_unrelated_decimal_call_not_yielded_as_match(self) -> None:
        # ``Decimal("0.42")`` is not a known canonical rate; the extractor
        # may yield it (the integration test then matches against the
        # law-constant index), but for this unit test we just confirm the
        # value is faithfully reported.
        values = self._values('Decimal("0.42")')
        self.assertEqual(values, [Decimal("0.42")])


if __name__ == "__main__":
    unittest.main()
