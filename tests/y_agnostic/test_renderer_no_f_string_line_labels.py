"""Structural test (slice W1.E / T3.2 from
``.review/2026-05-11-implementation-plan.md``): renderer code must
not construct form-line labels via f-strings.

Authority and rationale
-----------------------
Y2/P5 + invariant I3 enforce that every form-line label flowing into a
``FormEntry`` / ``legal_value_entry`` arrives via
``schema.label("<line_id>")`` — a name pinned in a
``tax_pipeline/forms/schemas/*.toml`` schema. New-2 (the
label-inventory ratchet at
``tests/test_label_inventory_verified.py``) catches user-facing
``Line N`` / ``Zeile N`` / ``Box N`` references in comments,
``notes=`` prose, narrative templates, and law-spec markdown.

Both defenses scan *string literals*. A renderer that constructs the
label dynamically with an f-string — e.g. ``f"Line {n}"`` where ``n``
is a runtime variable — sidesteps both:

* It is not a literal string the New-2 inventory regex catches.
* It is not a ``schema.label(...)`` call.

The result would be an arbitrary line number rendered to a form with
no verification trail. Today there are NO known cases of this in
``forms/usa.py`` or ``forms/germany.py``; the goal here is structural
prevention.

What this test does
-------------------
Walks ``tax_pipeline/forms/{usa,germany,filing_guide,common}.py`` and
inspects every ``ast.JoinedStr`` node (the AST representation of an
f-string). It flags any f-string whose constant prefix ends with a
form-line-label tag — ``Line ``, ``line ``, ``Zeile ``, ``Zeilen ``,
``Anlage ``, ``Box ``, ``Form `` followed immediately by a
``FormattedValue`` (the ``{expr}`` part).

Allow-list mechanism
--------------------
Some f-strings legitimately construct line *references* inside error
messages or narrative prose where the line number is known to be a
verified domain value (e.g., a country index in a per-country block
caption). The test recognizes a marker comment on the offending line
or the line above:

    # label-fstring-ok: <reason>

The reason is required and is part of the audit trail. Use this
sparingly — the structural intent is that label construction is
schema-driven, not f-string-driven.

Stdlib only — Python's ``ast`` module.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMS_DIR = REPO_ROOT / "tax_pipeline" / "forms"

# Renderer files in scope. New renderers added under
# ``tax_pipeline/forms/`` should be added here explicitly — the friction
# is deliberate, so a contributor reads this test before adding a new
# form module.
RENDERER_FILES: tuple[Path, ...] = (
    FORMS_DIR / "usa.py",
    FORMS_DIR / "germany.py",
    FORMS_DIR / "common.py",
    FORMS_DIR / "filing_guide.py",
)

# Tag tokens — when a constant prefix in an f-string ends with one of
# these (with the trailing space included), and the next part of the
# f-string is a ``FormattedValue`` (a ``{expr}`` placeholder), the
# f-string is flagged as a dynamically-constructed form-line label.
#
# The trailing space is required: it must be a clean ``"Line "``,
# ``"Zeile "``, etc., so unrelated prose like ``"Zeilenende"`` (a
# German word with ``Zeilen`` as a prefix) is not falsely matched.
LABEL_TAGS: tuple[str, ...] = (
    "Line ",
    "line ",
    "Zeile ",
    "Zeilen ",
    "Anlage ",
    "Box ",
    "Form ",
    "Schedule ",
)

# Marker comment that opts out a specific f-string. Must appear on the
# same source line as the f-string or on the line immediately above.
# The reason after the colon is required by convention (the test does
# not enforce non-emptiness — reviewer enforcement only).
ALLOW_MARKER = "# label-fstring-ok:"


def _ends_with_label_tag(text: str) -> str | None:
    """Return the matching tag if ``text`` ends with one of the
    label-tag tokens, otherwise ``None``.
    """
    for tag in LABEL_TAGS:
        if text.endswith(tag):
            return tag
    return None


def _line_or_above_has_marker(
    source_lines: list[str], lineno: int
) -> bool:
    """Return ``True`` if the source line at ``lineno`` (1-based) or
    the line immediately above contains the allow-list marker.
    """
    # ``lineno`` is 1-based per ``ast`` convention; ``source_lines`` is
    # 0-based.
    candidates = []
    if 1 <= lineno <= len(source_lines):
        candidates.append(source_lines[lineno - 1])
    if 2 <= lineno <= len(source_lines):
        candidates.append(source_lines[lineno - 2])
    return any(ALLOW_MARKER in line for line in candidates)


def _scan_file_for_label_fstrings(
    path: Path,
) -> list[tuple[int, str, str]]:
    """Return a list of ``(lineno, tag, snippet)`` tuples for every
    f-string in ``path`` whose constant prefix ends with a label tag
    immediately followed by a ``FormattedValue``, and which is NOT
    annotated with the allow-list marker.
    """
    text = path.read_text(encoding="utf-8")
    source_lines = text.splitlines()
    tree = ast.parse(text, filename=str(path))
    offenders: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        values = node.values
        # Walk adjacent (Constant, FormattedValue) pairs. We flag the
        # f-string if any ``ast.Constant`` whose ``.value`` is a string
        # ending in a label tag is immediately followed by an
        # ``ast.FormattedValue``.
        for i, part in enumerate(values):
            if not isinstance(part, ast.Constant):
                continue
            if not isinstance(part.value, str):
                continue
            tag = _ends_with_label_tag(part.value)
            if tag is None:
                continue
            if i + 1 >= len(values):
                continue
            next_part = values[i + 1]
            if not isinstance(next_part, ast.FormattedValue):
                continue
            # Match. Check the allow-list marker before recording.
            lineno = node.lineno
            if _line_or_above_has_marker(source_lines, lineno):
                continue
            # Reconstruct a short, human-readable snippet of the
            # offending f-string for the failure message. We include
            # the constant prefix that triggered the flag and the
            # textual rendering of the next ``FormattedValue``.
            try:
                snippet_expr = ast.unparse(next_part)
            except AttributeError:
                # ``ast.unparse`` is 3.9+. Fallback for safety.
                snippet_expr = "<expr>"
            snippet = f'f"...{part.value}{snippet_expr}..."'
            offenders.append((lineno, tag.strip(), snippet))
            # One flag per JoinedStr is enough; further (tag, expr)
            # pairs in the same f-string would surface together once
            # the first is fixed.
            break

    return offenders


class RendererNoFStringLineLabelsTest(unittest.TestCase):
    """Renderer code must not construct form-line labels via
    f-strings. See module docstring for the full rationale.
    """

    def test_no_label_fstrings_in_renderer_modules(self) -> None:
        all_offenders: list[str] = []
        for path in RENDERER_FILES:
            if not path.exists():
                # A renderer file listed in scope but missing on disk
                # is a real regression — the explicit scope list is
                # how the test stays honest as new renderers land.
                self.fail(
                    f"renderer module in scope is missing: {path}"
                )
            offenders = _scan_file_for_label_fstrings(path)
            rel = path.relative_to(REPO_ROOT)
            for lineno, tag, snippet in offenders:
                all_offenders.append(
                    f"{rel}:{lineno}: f-string constructs a form-line "
                    f"label with tag {tag!r}: {snippet}"
                )

        if all_offenders:
            joined = "\n  ".join(all_offenders)
            self.fail(
                "Form-line labels must come from "
                "schema.label('<line_id>') (Y2/P5 + invariant I3), not "
                "f-strings. The following f-strings construct a label "
                "dynamically and would bypass both the I3 AST scan and "
                "the New-2 label-inventory ratchet:\n  "
                f"{joined}\n\n"
                "Fix options:\n"
                "  1. Move the line label into the form schema TOML at "
                "tax_pipeline/forms/schemas/<form_id>.toml and read it "
                "via schema.label('<line_id>').\n"
                "  2. If the f-string is genuinely a narrative line "
                "reference (not a label written to a form line), add a "
                "marker comment on the same line or the line above:\n"
                "       # label-fstring-ok: <reason citing why this is "
                "a reference, not a schema label>\n"
            )


if __name__ == "__main__":
    unittest.main()
