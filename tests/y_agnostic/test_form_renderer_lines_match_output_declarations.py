"""Invariant I3: every form line a renderer touches must match an
``OutputDeclaration.form_line_refs`` somewhere in the rule graph.

Authority and rationale:

- § 32d Abs. 5 EStG governs the per-item foreign-tax credit and the
  ordering of the capital solidarity surcharge written on Anlage KAP.
  https://www.gesetze-im-internet.de/estg/__32d.html
- SolzG 1995 § 4 governs the capital solidarity surcharge.
  https://www.gesetze-im-internet.de/solzg_1995/__4.html
- IRS Pub. 514 worksheets self-document each Form 1116 line, the same
  contract on the U.S. side.
  https://www.irs.gov/publications/p514

The structural invariant: a form-renderer read of ``(form, line)`` must
match at least one ``OutputDeclaration`` whose ``form_line_refs``
declares the same ``(form, line)`` after whitespace / dash
normalization. The bidirectional check additionally flags
``OutputDeclaration.form_line_refs`` that no renderer consumes —
"orphan" declarations that surface stages whose form binding is dead
(for example, a stage classified ``DIAGNOSTIC_CROSS_CHECK`` whose
declared form line is, in fact, the line the renderer reads on
Anlage KAP).

This test is the RED half of the invariant; the paired WS-2B fix will
re-anchor DE25-17 ``section_32d1_gross_tax`` and DE25-19
``solidarity_surcharge`` onto the Anlage KAP line numbers the renderer
actually reads instead of leaving them orphan parallel declarations.

Two helper signatures are scanned:

1. ``_required_form_line(rows, form, line, …)`` — the legacy CSV-style
   form-line writer used in the Germany Anlage KAP / KAP-INV /
   KAP-INV-Bescheinigung renderers and the U.S. Pub. 514 worksheet
   renderers. Form / line strings are positional.
2. ``write_form(<paths>.usa_forms_root / f"{<paths>.year}_<form>.md", …,
   [legal_value_entry("Line N", lv_*(…), …, source="us-treaty-package.json"),
   …], …)`` — the F-CQ-1 / I11 form-line boundary used by every U.S.
   form renderer. The form name resolves from the file-path literal
   (``<form>`` mapped to a canonical name — e.g. ``schedule_8812`` →
   ``"Schedule 8812"``); the line label resolves from the first
   positional argument of ``legal_value_entry``.

Both are equivalent for the bidirectional invariant — every renderer
write site must correspond to a declared ``form_line_refs`` entry, and
every declared entry must have a renderer consumer.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import Mapping

from tax_pipeline.forms._schema import iter_schema_form_ids, load_form_schema
from tax_pipeline.y2025.germany_stages import germany_law_stages_2025
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GERMANY_FORMS_PATH = PROJECT_ROOT / "tax_pipeline" / "forms" / "germany.py"
USA_FORMS_PATH = PROJECT_ROOT / "tax_pipeline" / "forms" / "usa.py"

# AST helper-call names that take ``(rows, form, line, …)`` signatures.
_FORM_LINE_HELPERS = frozenset({"_required_form_line"})

# Whitespace + dash normalization. Per the migration plan: strip
# leading/trailing whitespace, collapse internal whitespace, treat the
# em-dash and hyphen as equivalent.
_DASH_TRANSLATION = str.maketrans({"—": "-"})
_INNER_WS = re.compile(r"\s+")

# Mapping from ``f"{paths.year}_<form>.md"`` template stems to the
# canonical form-name string used in ``OutputDeclaration.form_line_refs``.
# Adding a new U.S. form renderer requires exactly one new row here so
# the I3 invariant scanner picks up its ``legal_value_entry`` form-line
# writes. Authority for each canonical name is the IRS form/instruction
# landing page; the canonical strings match the ``form="..."`` values
# declared in ``tax_pipeline/y2025/us_stages.py`` /
# ``treaty_2025_stages.py`` ``FormLineRef`` constructors.
_USA_FORM_FILE_STEM_TO_CANONICAL: dict[str, str] = {
    "1040": "Form 1040",
    "schedule_1": "Schedule 1",
    "schedule_2": "Schedule 2",
    "schedule_3": "Schedule 3",
    "schedule_b": "Schedule B",
    "schedule_c": "Schedule C",
    "schedule_d": "Schedule D",
    "schedule_se": "Schedule SE",
    "schedule_8812": "Schedule 8812",
    "form_8949": "Form 8949",
    "form_6781": "Form 6781",
    "form_6251": "Form 6251",
    "form_8959": "Form 8959",
    "form_8960": "Form 8960",
    "form_1116_passive": "Form 1116 Passive",
    "form_1116_general": "Form 1116 General",
    # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): separate Form 1116 for
    # § 904(d)(6) treaty-resourced basket (``2025_form_1116_resourced.md``).
    "form_1116_resourced": "Form 1116 Resourced",
    # C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 2555 (FEIE election).
    # The ``_write_form_2555`` renderer is gated on
    # ``elections.elect_section_911_feie=true``; when not elected the
    # form file is absent (fail-closed). Scanner detects the
    # ``legal_value_entry("Line 36"|"Line 45"|"Line 50", ...)`` writes
    # via the path-based stem regardless of gating because static AST
    # analysis sees the literal write_form call site.
    "form_2555": "Form 2555",
}

# Match ``"Line N"`` / ``"Line 16a"`` etc.; non-line entries (e.g.,
# ``"Total credit"``, ``"40% short-term portion"``) are skipped because
# they are display labels, not form-line numbers.
_LINE_LABEL_RE = re.compile(r"^Line\s+([0-9A-Za-z]+)\s*$")
# Match ``f"{<name>.year}_<stem>.md"`` for the ``write_form`` path arg.
_FORM_FILE_STEM_RE = re.compile(r"^_(?P<stem>[A-Za-z0-9_]+)\.md$")
# C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): German renderer label
# format places the form name AND the Zeile in a single label string
# (e.g. ``"Anlage Vorsorgeaufwand Zeilen 4-9"``,
# ``"Anlage KAP-INV Zeile 26"``, ``"Anlage Kind Zeile 65"``). The
# scanner extracts ``(form, line)`` from the label itself rather than
# from the write_form path stem (the path stem only gates which
# renderer is being scanned). Labels prefixed with ``(audit)`` /
# ``(cross-check)`` are deliberately skipped — those rows surface
# values for audit traceability and do NOT correspond to a Zeile the
# Finanzamt expects on the printed form.
#
# The form name token follows the leading ``Anlage`` keyword and runs
# until ``Zeile`` / ``Zeilen``; the line token captures one or more
# digit ranges (``"4-9"``, ``"41-47"`` from Anlage SO crypto block,
# ``"6-15"`` from Anlage Kind, ``"9-13"`` from Anlage KAP-INV).
_GERMAN_LINE_LABEL_RE = re.compile(
    r"^Anlage\s+(?P<form>.+?)\s+Zeilen?\s+(?P<line>[0-9A-Za-z\-/\s]+?)\s*$"
)


def _normalize(text: str) -> str:
    return _INNER_WS.sub(" ", text.translate(_DASH_TRANSLATION).strip())


def _normalized_pair(form: str, line: str) -> tuple[str, str]:
    return (_normalize(form), _normalize(line))


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _collect_person_slot_dicts(tree: ast.AST) -> list[dict[str, ast.AST]]:
    """Find dict literals carrying ``anlage_kap_label`` + ``kap_lines``.

    The renderer's ``_german_person_slots`` returns per-person slot
    dicts; ``_required_form_line(rows, person["anlage_kap_label"],
    line, …)`` iterates ``person["kap_lines"]``. We resolve that
    label/line cross-product statically.
    """
    slot_dicts: list[dict[str, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys: dict[str, ast.AST] = {}
        for key_node, value_node in zip(node.keys, node.values):
            text_key = _string_constant(key_node) if key_node is not None else None
            if text_key is not None:
                keys[text_key] = value_node
        if "anlage_kap_label" in keys and "kap_lines" in keys:
            slot_dicts.append(keys)
    return slot_dicts


def _list_of_string_constants(node: ast.AST) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out: list[str] = []
    for element in node.elts:
        text = _string_constant(element)
        if text is None:
            return None
        out.append(text)
    return out


def _path_root_attribute_name(node: ast.AST) -> str | None:
    """Return the ``<name>_forms_root`` attribute of the LHS of a path
    BinOp.

    For ``paths.usa_forms_root / f"{paths.year}_<stem>.md"`` this returns
    ``"usa_forms_root"``; for the German variant
    ``paths.germany_forms_root / ...`` it returns ``"germany_forms_root"``.
    Used to discriminate U.S. vs. Germany write_form sites.
    """
    if not isinstance(node, ast.Attribute):
        return None
    return node.attr


def _resolve_write_form_path_arg(node: ast.AST) -> str | None:
    """Resolve ``write_form``'s first positional arg to a form-file stem.

    The U.S. renderer always builds the destination path as
    ``paths.usa_forms_root / f"{paths.year}_<stem>.md"``. We unwrap the
    binary ``/`` operator and read the f-string's literal portion.
    Returns the canonical form name from
    ``_USA_FORM_FILE_STEM_TO_CANONICAL`` or ``None`` if the path
    expression doesn't match the expected shape.
    """
    if not isinstance(node, ast.BinOp):
        return None
    # The right operand is the f-string ``f"{paths.year}_<stem>.md"``.
    right = node.right
    if not isinstance(right, ast.JoinedStr):
        return None
    # Scan the f-string parts for the literal piece ``"_<stem>.md"`` (the
    # ``{paths.year}`` formatted value comes through as a FormattedValue,
    # not a Constant).
    literal_text = "".join(
        part.value
        for part in right.values
        if isinstance(part, ast.Constant) and isinstance(part.value, str)
    )
    match = _FORM_FILE_STEM_RE.match(literal_text)
    if match is None:
        return None
    stem = match.group("stem")
    return _USA_FORM_FILE_STEM_TO_CANONICAL.get(stem)


def _is_germany_write_form_path(node: ast.AST) -> bool:
    """Return True if ``node`` is a ``paths.germany_forms_root / ...``
    BinOp expression. The German renderer uses label-encoded form +
    Zeile (``"Anlage Vorsorgeaufwand Zeilen 4-9"``) so the I3 scanner
    extracts ``(form, line)`` from the label itself rather than from
    the path stem.
    """
    if not isinstance(node, ast.BinOp):
        return False
    return _path_root_attribute_name(node.left) == "germany_forms_root"


def _german_legal_value_entry_pair(
    call: ast.Call,
    *,
    schema_var_to_form_id: Mapping[str, str],
) -> tuple[str, str] | None:
    """Return ``(form_name, line)`` extracted from the first positional
    argument of a German-renderer ``legal_value_entry`` call.

    Recognized formats:
    - ``"Anlage Vorsorgeaufwand Zeilen 4-9"`` →
      ``("Anlage Vorsorgeaufwand", "4-9")``
    - ``"Anlage KAP-INV Zeile 26"`` →
      ``("Anlage KAP-INV", "26")``
    - ``"Anlage Kind Zeile 65"`` →
      ``("Anlage Kind", "65")``

    Resolves both inline-string and schema-driven (``schema.label("X")``)
    first arguments — see :func:`_resolve_first_arg_label`.

    Audit-only rows (labels containing ``(audit)`` or ``(cross-check)``)
    return ``None`` and are skipped — those rows surface values for
    audit traceability and do NOT correspond to a Zeile on the printed
    form. Labels that don't match the ``Anlage <X> Zeile(n) <N>``
    pattern at all also return ``None`` (e.g. ``"Anlage AUS — Status"``,
    ``"Hauptvordruck (Identifikation)"``).
    """
    label = _resolve_first_arg_label(
        call, schema_var_to_form_id=schema_var_to_form_id
    )
    if label is None:
        return None
    stripped = label.strip()
    # Audit-only rows are deliberately skipped — they exist on the
    # rendered package for traceability but the Finanzamt does not
    # expect a value on a corresponding Zeile.
    if "(audit)" in stripped or "(cross-check)" in stripped:
        return None
    match = _GERMAN_LINE_LABEL_RE.match(stripped)
    if match is None:
        return None
    form = "Anlage " + match.group("form").strip()
    line = match.group("line").strip()
    return form, line


def _resolve_first_arg_label(
    call: ast.Call,
    *,
    schema_var_to_form_id: Mapping[str, str],
) -> str | None:
    """Resolve the first positional argument of a ``legal_value_entry``
    call to a literal label string.

    Two sources are recognized:

    1. **Inline string literal** — ``legal_value_entry("Line 16", ...)``.
       Returned as-is.
    2. **Schema-driven label** (Y2 / P5) — ``legal_value_entry(
       schema.label("16"), ...)`` where ``schema`` was bound by
       ``schema = load_form_schema("form_1040")``. The scanner reads
       ``tax_pipeline/forms/schemas/form_1040.toml`` and returns the
       declared label for line_id ``"16"``. Allows the form-schema-as-
       data refactor without losing the I3 AST scan.

    Returns the label string, or ``None`` if the first argument cannot
    be statically resolved (e.g. concatenated strings, conditional
    expressions, or schema lookups whose schema variable cannot be
    resolved).
    """
    if not call.args:
        return None
    arg = call.args[0]
    label = _string_constant(arg)
    if label is not None:
        return label
    # ``schema.label("X")`` Attribute Call — only resolve if the
    # ``schema`` variable was bound by ``load_form_schema("<form_id>")``.
    if (
        isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "label"
        and isinstance(arg.func.value, ast.Name)
        and len(arg.args) == 1
    ):
        schema_var_name = arg.func.value.id
        line_id = _string_constant(arg.args[0])
        if line_id is None:
            return None
        form_id = schema_var_to_form_id.get(schema_var_name)
        if form_id is None:
            return None
        schema = load_form_schema(form_id)
        try:
            return schema.label(line_id)
        except KeyError:
            return None
    return None


def _legal_value_entry_line_label(
    call: ast.Call,
    *,
    schema_var_to_form_id: Mapping[str, str],
) -> str | None:
    """Return the bare line label (e.g., ``"5"`` or ``"16a"``) from the
    first positional argument of a ``legal_value_entry`` call. Non-line
    labels (``"Total credit"``, ``"Net section 1256 result"``, etc.)
    return ``None`` and are skipped from the I3 scan because they are
    display labels rather than statutory form lines.

    Resolves both inline-string and schema-driven (``schema.label("16")``)
    first arguments — see :func:`_resolve_first_arg_label`.
    """
    label = _resolve_first_arg_label(
        call, schema_var_to_form_id=schema_var_to_form_id
    )
    if label is None:
        return None
    match = _LINE_LABEL_RE.match(label.strip())
    if match is None:
        return None
    return match.group(1)


def _bindings_in_subtree(node: ast.AST) -> dict[str, str]:
    """Collect ``<name> = load_form_schema("<form_id>")`` assignments
    inside ``node``'s subtree (typically a function body) and return
    them as ``{<name>: <form_id>}``.

    Schemas are loaded inside renderer functions (one schema =
    load_form_schema(...) per renderer function), so binding scope is
    function-level: each renderer rebinds the name ``schema`` to its
    own form_id. The I3 scanner walks each ``write_form(...)`` site,
    discovers the enclosing function, and resolves the schema variable
    against bindings inside that function only. This stops the
    last-write-wins flat-map issue when multiple renderers share the
    same variable name.
    """
    bindings: dict[str, str] = {}
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign):
            continue
        value = sub.value
        if (
            not isinstance(value, ast.Call)
            or not isinstance(value.func, ast.Name)
            or value.func.id != "load_form_schema"
            or len(value.args) != 1
        ):
            continue
        form_id = _string_constant(value.args[0])
        if form_id is None:
            continue
        for target in sub.targets:
            if isinstance(target, ast.Name):
                bindings[target.id] = form_id
    return bindings


def _build_function_binding_index(
    tree: ast.AST,
) -> tuple[
    dict[int, dict[str, str]],
    dict[int, int],
]:
    """Return two dicts:

    1. ``func_bindings``: ``id(FunctionDef) -> {var_name: form_id}`` —
       per-function schema bindings.
    2. ``call_to_func``: ``id(Call) -> id(FunctionDef)`` — for every
       Call node, which enclosing FunctionDef contains it.

    This lets the scanner resolve ``schema.label("X")`` calls against
    bindings inside the enclosing renderer function, ignoring schema
    loads in unrelated renderers.
    """
    func_bindings: dict[int, dict[str, str]] = {}
    call_to_func: dict[int, int] = {}

    def _walk_func(func: ast.AST) -> None:
        bindings = _bindings_in_subtree(func)
        func_bindings[id(func)] = bindings
        for sub in ast.walk(func):
            if isinstance(sub, ast.Call):
                call_to_func[id(sub)] = id(func)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not func:
                _walk_func(sub)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if id(node) not in func_bindings:
                _walk_func(node)
    return func_bindings, call_to_func


def _collect_legal_value_entry_reads(tree: ast.AST) -> set[tuple[str, str]]:
    """``(form, line)`` pairs the renderer writes via
    ``write_form(path, title, posture, [legal_value_entry(<label>,
    lv_*(…), …), …], notes)``.

    Two label conventions are handled:

    1. **U.S. renderer** — form name is resolved from the
       ``paths.usa_forms_root / f"{paths.year}_<stem>.md"`` path; line
       is the bare ``"Line N"`` first positional argument of
       ``legal_value_entry``.
    2. **German renderer** (C-audit, FORM-MAPPING-FOLLOWUP, 2026-05-04)
       — form name AND Zeile both live in the first positional
       argument of ``legal_value_entry`` (e.g.
       ``"Anlage Vorsorgeaufwand Zeilen 4-9"``,
       ``"Anlage KAP-INV Zeile 26"``). The path-LHS attribute
       (``paths.germany_forms_root``) gates which scanner branch fires.
       Audit rows (``(audit)`` / ``(cross-check)`` in the label) are
       skipped because the Finanzamt does not expect a value on a
       corresponding Zeile for those.

    Both branches enforce the F-CQ-1 / I11 boundary — see CLAUDE.md
    invariant I11. Each branch resolves both inline-string labels and
    Y2 / P5 schema-driven labels (``schema = load_form_schema("X");
    legal_value_entry(schema.label("16"), ...)``) — see
    :func:`_resolve_first_arg_label`. Schema-variable bindings are
    resolved per enclosing renderer function so multiple renderers can
    rebind the same ``schema`` name without cross-talk.
    """
    func_bindings, call_to_func = _build_function_binding_index(tree)
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "write_form"):
            continue
        if len(node.args) < 4:
            continue
        # Resolve schema variable bindings against the enclosing
        # FunctionDef. Falls back to an empty map for module-level
        # write_form calls (none today, but kept for forward compat).
        enclosing_func_id = call_to_func.get(id(node))
        schema_var_to_form_id: Mapping[str, str] = (
            func_bindings.get(enclosing_func_id, {})
            if enclosing_func_id is not None
            else {}
        )
        # The 4th positional arg is the entries list. Walk it for every
        # ``legal_value_entry(...)`` call (legacy ``FormEntry(...)``
        # calls without a line label are documentation-style row
        # entries, not statutory form-line writes — they remain out of
        # scope for I3).
        entries_node = node.args[3]
        if _is_germany_write_form_path(node.args[0]):
            for sub in ast.walk(entries_node):
                if not isinstance(sub, ast.Call):
                    continue
                if not (
                    isinstance(sub.func, ast.Name) and sub.func.id == "legal_value_entry"
                ):
                    continue
                pair = _german_legal_value_entry_pair(
                    sub, schema_var_to_form_id=schema_var_to_form_id
                )
                if pair is None:
                    continue
                form_name, line = pair
                pairs.add(_normalized_pair(form_name, line))
            continue
        form_name = _resolve_write_form_path_arg(node.args[0])
        if form_name is None:
            continue
        for sub in ast.walk(entries_node):
            if not isinstance(sub, ast.Call):
                continue
            if not (isinstance(sub.func, ast.Name) and sub.func.id == "legal_value_entry"):
                continue
            line = _legal_value_entry_line_label(
                sub, schema_var_to_form_id=schema_var_to_form_id
            )
            if line is None:
                continue
            pairs.add(_normalized_pair(form_name, line))
    return pairs


def _collect_renderer_reads(path: Path) -> set[tuple[str, str]]:
    """``(form, line)`` pairs the renderer reads.

    Two shapes are detected:

    1. ``_required_form_line(rows, form, line, …)`` — legacy CSV-style
       form-line writer. Both string-constant and
       ``person["anlage_kap_label"]`` / loop-line variants are resolved
       statically.
    2. ``write_form(<path>, title, posture, [legal_value_entry("Line N",
       lv_*(…), …)], …)`` — F-CQ-1 / I11 form-line boundary used by every
       U.S. form renderer. Form name resolves from the
       ``paths.usa_forms_root / f"{paths.year}_<stem>.md"`` path; line
       label resolves from the first positional argument of
       ``legal_value_entry``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pairs: set[tuple[str, str]] = set()

    person_slot_dicts = _collect_person_slot_dicts(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        helper_name = (
            func.attr if isinstance(func, ast.Attribute)
            else func.id if isinstance(func, ast.Name)
            else None
        )
        if helper_name not in _FORM_LINE_HELPERS:
            continue
        if len(node.args) < 3:
            continue
        form_node, line_node = node.args[1], node.args[2]
        form_const = _string_constant(form_node)
        line_const = _string_constant(line_node)
        if form_const is not None and line_const is not None:
            pairs.add(_normalized_pair(form_const, line_const))
            continue
        # Heuristic: form is ``<name>["anlage_kap_label"]`` and line is
        # a Name bound by an enclosing comprehension over
        # ``<name>["kap_lines"]`` or ``<name>.get("kap_raw_lines", …)``.
        # Cross-product against all dict literals that carry both keys.
        if (
            isinstance(form_node, ast.Subscript)
            and _string_constant(form_node.slice) == "anlage_kap_label"
            and isinstance(line_node, ast.Name)
        ):
            for slot in person_slot_dicts:
                label = _string_constant(slot["anlage_kap_label"])
                lines = _list_of_string_constants(slot["kap_lines"])
                if label is None or lines is None:
                    continue
                for line in lines:
                    pairs.add(_normalized_pair(label, line))
    pairs |= _collect_legal_value_entry_reads(tree)
    return pairs


def _collect_declared_pairs() -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Index every ``OutputDeclaration.form_line_refs`` from the three
    jurisdictions by normalized ``(form, line)``, listing originating
    ``(stage_id, output_key)`` for concrete failure messages.
    """
    declared: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for stages in (
        germany_law_stages_2025(),
        usa_law_stages_2025(),
        treaty_law_stages_2025(),
    ):
        for stage in stages:
            for declaration in stage.outputs:
                for ref in declaration.form_line_refs:
                    key = _normalized_pair(ref.form, ref.line)
                    declared.setdefault(key, []).append(
                        (stage.stage_id, declaration.key)
                    )
    return declared


def _forms_with_any_declared_line(
    declared_pairs: Mapping[tuple[str, str], list[tuple[str, str]]],
) -> set[str]:
    """Return the set of normalized form names that have at least one
    ``OutputDeclaration.form_line_refs`` entry. The bidirectional
    invariant is enforced ONLY on these forms: the moment any rule
    declares a form-line ref for a form, every renderer write to that
    form must be declared. Forms with zero declarations remain in the
    legacy "renderer-only" posture (Form 1040 / Form 6251 / etc.) until
    a future workstream surfaces their values as declared rule outputs.
    """
    return {form for form, _line in declared_pairs.keys()}


class FormRendererLinesMatchOutputDeclarationsTest(unittest.TestCase):
    """Bidirectional renderer↔OutputDeclaration form-line invariant."""

    def test_renderer_reads_match_some_output_declaration(self) -> None:
        renderer_reads = _collect_renderer_reads(GERMANY_FORMS_PATH)
        renderer_reads |= _collect_renderer_reads(USA_FORMS_PATH)
        self.assertTrue(
            renderer_reads,
            "AST scan failed to find any _required_form_line(rows, form, line, …) "
            "or write_form([legal_value_entry(...)]) calls in the form "
            "renderers; check helper names changed.",
        )
        declared = _collect_declared_pairs()
        declared_pairs = set(declared)
        scanned_forms = _forms_with_any_declared_line(declared)
        # Bidirectional gating: only enforce "every renderer read is
        # declared" for forms that already opt into the invariant by
        # declaring AT LEAST ONE form_line_ref. Adding the first
        # FormLineRef(form="<X>", ...) anywhere in the rule graph turns
        # form X into a scanned form — every write_form([legal_value_entry])
        # site for X must then have a matching declaration. This makes
        # the bidirectional contract the default for new renderers
        # (Schedule 8812) without requiring legacy renderers (Form 1040,
        # Form 6251) to be retrofitted in the same change.
        unmatched_reads = sorted(
            (form, line)
            for (form, line) in renderer_reads
            if form in scanned_forms and (form, line) not in declared_pairs
        )
        if unmatched_reads:
            joined = "\n".join(
                f"  - renderer reads ({form!r}, {line!r}) but no OutputDeclaration "
                "declares this (form, line)"
                for form, line in unmatched_reads
            )
            self.fail(
                "Form-renderer reads are not anchored to any OutputDeclaration "
                f"form_line_refs. {len(unmatched_reads)} unmatched pair(s):\n"
                f"{joined}"
            )

    def test_output_declaration_form_lines_have_renderer_consumer(self) -> None:
        renderer_reads = _collect_renderer_reads(GERMANY_FORMS_PATH)
        renderer_reads |= _collect_renderer_reads(USA_FORMS_PATH)
        declared = _collect_declared_pairs()
        orphans = sorted(
            (pair, sources)
            for pair, sources in declared.items()
            if pair not in renderer_reads
        )
        if not orphans:
            return
        # Acceptance focus per WS-3: DE25-17 (§ 32d Abs. 1 EStG gross
        # tax) and DE25-19 (§ 4 SolzG 1995 capital soli) declare Anlage
        # KAP form lines in parallel with a DIAGNOSTIC_CROSS_CHECK
        # audit waypoint, but no renderer reads the declared line —
        # the form binding is dead and the stage is effectively
        # diagnostic-only despite the form_line_refs entry.
        focus_ids = {"DE25-17-SECTION-32D1-GROSS-TAX", "DE25-19-CAPITAL-SOLI"}
        focus, other = [], []
        for (form, line), sources in orphans:
            sources_text = ", ".join(f"{sid}::{key}" for sid, key in sources)
            entry = (
                f"  - OutputDeclaration ({form!r}, {line!r}) declared by "
                f"{sources_text} but no renderer reads it"
            )
            (focus if any(sid in focus_ids for sid, _ in sources) else other).append(entry)
        parts = [
            "OutputDeclaration form_line_refs without a renderer consumer "
            "(orphan declarations indicate stages classified as "
            "DIAGNOSTIC_CROSS_CHECK whose declared form line is in fact the "
            "line the renderer reads on Anlage KAP — see § 32d Abs. 5 EStG / "
            "§ 4 SolzG 1995):"
        ]
        if focus:
            parts.append("DE25-17 / DE25-19 acceptance focus:")
            parts.extend(focus)
        if other:
            parts.append("Additional orphan declarations:")
            parts.extend(other)
        self.fail("\n".join(parts))


def _schema_line_keys_for_form(form_id: str) -> set[tuple[str, str]]:
    """Return ``{(canonical_form_name, statutory_line)}`` extracted from
    every line in the schema for ``form_id``.

    Two extractions are tried for each schema entry:

    1. ``line_id`` directly (works for U.S. forms whose schema declares
       ``line_id="16"`` matching ``FormLineRef.line="16"``).
    2. statutory line tag extracted from ``label`` via the I3 regexes
       (works for German Anlagen whose schema declares
       ``line_id="zeilen_4_9"`` + ``label="Anlage Vorsorgeaufwand
       Zeilen 4-9"`` matching ``FormLineRef.line="4-9"``).

    Returning *both* into the cross-check set lets the I3 strengthened
    check accept either schema convention without forcing a unified
    line_id naming scheme across all forms in this commit.
    """
    schema = load_form_schema(form_id)
    keys: set[tuple[str, str]] = set()
    canonical = schema.canonical_form_name
    for line in schema.lines:
        if line.unused:
            continue
        # 1) Direct line_id match (US convention).
        keys.add(_normalized_pair(canonical, line.line_id))
        # 2) Label-extracted statutory tag (German convention).
        stripped = line.label.strip()
        m_us = _LINE_LABEL_RE.match(stripped)
        if m_us is not None:
            keys.add(_normalized_pair(canonical, m_us.group(1)))
        m_de = _GERMAN_LINE_LABEL_RE.match(stripped)
        if m_de is not None:
            extracted_form = "Anlage " + m_de.group("form").strip()
            extracted_line = m_de.group("line").strip()
            # If the extracted form matches the schema's canonical name
            # (modulo normalization), record the statutory line.
            if _normalize(extracted_form) == _normalize(canonical):
                keys.add(_normalized_pair(canonical, extracted_line))
    return keys


def _all_schema_line_keys() -> set[tuple[str, str]]:
    """Aggregate every schema line key across every schema in
    ``tax_pipeline/forms/schemas/``.
    """
    keys: set[tuple[str, str]] = set()
    for form_id in iter_schema_form_ids():
        keys |= _schema_line_keys_for_form(form_id)
    return keys


def _all_schema_canonical_form_names() -> set[str]:
    """Set of normalized ``canonical_form_name`` values across all
    schemas. Used to gate the strengthened I3 check: only declared
    rules whose form has a schema are cross-checked. Forms without a
    schema fall back to the older bidirectional checks.
    """
    return {
        _normalize(load_form_schema(form_id).canonical_form_name)
        for form_id in iter_schema_form_ids()
    }


def _collect_schema_label_consumptions(path: Path) -> set[tuple[str, str]]:
    """Return ``{(form_id, line_id)}`` pairs the renderer at ``path``
    consumes via ``schema.label("<line_id>")`` where ``schema`` was
    bound by ``load_form_schema("<form_id>")`` in the same enclosing
    function.

    Two consumption shapes are detected:

    1. **Direct literal** — ``schema.label("16")`` resolves immediately.
    2. **Dynamic-line dispatch** — ``schema.label(line)`` inside a
       function whose ``schema`` is bound to ``"anlage_kap"`` and where
       ``line`` is a comprehension variable iterating ``kap_lines`` from
       module-level person-slot dict literals (the existing
       ``_collect_person_slot_dicts`` helper). The schema-orphan check
       cross-products the schema variable's ``form_id`` with every
       known ``kap_lines`` element so dynamic-line dispatch does not
       falsely flag the per-Zeile schema entries as orphans. (Mirrors
       :func:`_collect_renderer_reads`'s person-slot cross-product
       branch — both scanners must see the same consumption set or
       the schema-side check disagrees with the renderer-side check.)

    Reuses :func:`_build_function_binding_index` so the per-renderer
    binding scope is identical to the legacy renderer-read scanner.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    func_bindings, call_to_func = _build_function_binding_index(tree)
    person_slot_dicts = _collect_person_slot_dicts(tree)
    person_slot_kap_lines: set[str] = set()
    for slot in person_slot_dicts:
        lines = _list_of_string_constants(slot["kap_lines"])
        if lines is None:
            continue
        person_slot_kap_lines.update(lines)
        # Anlage KAP renderer also unconditionally prepends "4" — keep
        # the consumption set in sync with the actual renderer body
        # (see _write_anlage_kap_for_person).
        person_slot_kap_lines.add("4")
    consumed: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "label"
            and isinstance(func.value, ast.Name)
            and len(node.args) == 1
        ):
            continue
        enclosing_func_id = call_to_func.get(id(node))
        if enclosing_func_id is None:
            continue
        bindings = func_bindings.get(enclosing_func_id, {})
        form_id = bindings.get(func.value.id)
        if form_id is None:
            continue
        line_id = _string_constant(node.args[0])
        if line_id is not None:
            consumed.add((form_id, line_id))
            continue
        # Dynamic-line dispatch: schema.label(<Name>). For the Anlage
        # KAP person-slot pattern, surface every kap_lines entry as
        # consumed — the I3 reverse check otherwise red-flags the
        # 14 Zeile schema entries that are dispatched at runtime.
        if isinstance(node.args[0], ast.Name) and form_id == "anlage_kap":
            for line_id in person_slot_kap_lines:
                consumed.add((form_id, line_id))
    return consumed


def _all_schema_label_consumptions() -> set[tuple[str, str]]:
    """Aggregate ``schema.label(...)`` consumption pairs across both
    renderer modules.
    """
    consumed = _collect_schema_label_consumptions(GERMANY_FORMS_PATH)
    consumed |= _collect_schema_label_consumptions(USA_FORMS_PATH)
    return consumed


class FormSchemaLinesMatchOutputDeclarationsTest(unittest.TestCase):
    """Phase 3 strengthening of I3 — schema lines and OutputDeclaration
    form_line_refs must agree.

    Once every form has a schema (Phase 2 complete), every
    ``FormLineRef(form, line, …)`` whose ``form`` matches a schema's
    ``canonical_form_name`` must point at a declared schema line. This
    catches the year-on-year drift class described in the
    2026-05-08 platform review (Schedule 8812 reshuffled lines in 2022
    and 2024; Form 1040 lines 26/27/28 ordering tweaked in 2023): a
    rule-graph reshuffle that does not also touch the schema fails
    here, loud, at test time.

    The check only fires for forms that have a schema. Forms without a
    schema continue to rely on the older bidirectional renderer-vs-
    OutputDeclaration check (the two existing tests above).
    """

    def test_every_form_line_ref_points_at_a_schema_line(self) -> None:
        schema_keys = _all_schema_line_keys()
        schema_forms = _all_schema_canonical_form_names()
        declared = _collect_declared_pairs()
        orphans: list[tuple[tuple[str, str], list[tuple[str, str]]]] = []
        for (form, line), sources in declared.items():
            if form not in schema_forms:
                # No schema declared for this form yet — skip; the older
                # bidirectional check still covers renderer agreement.
                continue
            if (form, line) in schema_keys:
                continue
            orphans.append(((form, line), sources))
        if not orphans:
            return
        joined = "\n".join(
            f"  - FormLineRef ({form!r}, {line!r}) declared by "
            + ", ".join(f"{sid}::{key}" for sid, key in sources)
            + f" — schema for form {form!r} does not declare a line "
            "with this line_id (or matching label tag)"
            for (form, line), sources in orphans
        )
        self.fail(
            "Y2 / P5 strengthened I3: rule-graph form_line_refs missing "
            "from the matching form schema (the schema must be the "
            "single source of truth for line numbers — a 2026 IRS / "
            "ELSTER renumber is a TOML edit, NOT an OutputDeclaration "
            f"reshuffle without a schema update). {len(orphans)} "
            f"orphan(s):\n{joined}"
        )

    def test_every_schema_line_is_consumed_by_a_renderer(self) -> None:
        """Phase 3 reverse direction: every declared schema line
        (``unused=false``) must be consumed by at least one
        ``schema.label("<line_id>")`` call in the renderer.

        Without this, a TOML ``[[lines]]`` entry that no renderer reads
        is dead — it can't drift loud at test time, so a 2026 schema
        addition that nobody hooked into the renderer would silently
        coexist with the rest of the form. The schema-as-data contract
        is bidirectional: rule-graph form_line_refs must point at a
        schema line, AND every schema line must carry through to the
        rendered Markdown via ``schema.label(...)``.

        Lines explicitly opted out via ``unused = true`` (with a
        non-empty ``reason``) are skipped — that's the documented
        escape hatch for declared-but-not-yet-consumed entries.
        """
        consumed = _all_schema_label_consumptions()
        orphans: list[tuple[str, str]] = []
        for form_id in iter_schema_form_ids():
            schema = load_form_schema(form_id)
            for line in schema.lines:
                if line.unused:
                    continue
                if (form_id, line.line_id) in consumed:
                    continue
                orphans.append((form_id, line.line_id))
        if not orphans:
            return
        joined = "\n".join(
            f"  - schema {form_id!r} declares line_id={line_id!r} but no "
            "renderer reads schema.label(<line_id>) for it"
            for form_id, line_id in sorted(orphans)
        )
        self.fail(
            "Y2 / P5 strengthened I3 (reverse): schema lines without a "
            "renderer consumer (the schema-as-data contract is "
            "bidirectional — every declared line must be read via "
            "schema.label(...), or marked unused=true with a reason). "
            f"{len(orphans)} orphan schema line(s):\n{joined}"
        )


if __name__ == "__main__":
    unittest.main()
