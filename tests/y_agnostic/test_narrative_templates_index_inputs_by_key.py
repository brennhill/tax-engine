from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "tax_pipeline" / "narrative" / "templates"

# Match ``rule.inputs[<int>]`` (with optional whitespace inside the brackets).
# Catches the canonical positional-index access pattern that broke during the
# WS-3A redo when DE25-07-TAXABLE-INCOME's ``input_fact_keys`` shifted.
POSITIONAL_INPUT_PATTERN = re.compile(r"rule\.inputs\[\s*\d+\s*\]")

# Match ``xs[<int>]`` where ``xs`` was assigned from ``rule.inputs`` earlier
# in the template (a Jinja ``{% set xs = rule.inputs %}`` followed by
# ``{{ xs[2].value }}`` is the same positional-index hazard, just one
# rename removed). The detector flags any local-name reassignment of
# ``rule.inputs`` and then any ``<that-name>[<int>]`` subsequent access.
POSITIONAL_VIA_LOCAL_SET_PATTERN = re.compile(
    r"\{%\s*set\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*rule\.inputs\s*[%-]?\}"
)

# Match ``rule.inputs|first`` and ``rule.inputs|last`` and ``rule.inputs|nth(N)``
# Jinja filters. ``|first`` and ``|last`` are positional-by-index in disguise
# (first element of input_fact_keys); ``|nth(N)`` is the same hazard as
# ``[N]``.
JINJA_POSITIONAL_FILTER_PATTERN = re.compile(
    r"rule\.inputs\s*\|\s*(?:first|last|nth\s*\(\s*\d+\s*\))"
)

# Templates may opt out by including this pragma comment if (and only if)
# there is a documented reason positional indexing is correct. WS-5G expects
# zero allowlisted templates today.
PRAGMA_ALLOWLIST = "{# pragma: positional-input-ok #}"


class NarrativeTemplatesIndexInputsByKeyTest(unittest.TestCase):
    """Invariant I12 (docs/invariant-migration-plan.md §7 WS-5G): narrative
    templates must address inputs by their declared fact key, never by
    positional index.

    Why this matters: ``LawStage.input_fact_keys`` is a tuple. Templates used
    to read ``{{ rule.inputs[2].value }}`` which is the third element of that
    tuple. Adding a new entry to a stage's ``input_fact_keys`` (perfectly
    valid per CLAUDE.md tax-rule discipline — declaring a previously implicit
    fact read makes the audit graph more honest) silently shifted those
    indices and corrupted template rendering. The WS-3A redo hit exactly this:
    DE25-07-TAXABLE-INCOME crashed with JSONDecodeError when a new declared
    input was prepended to its tuple.

    The fix is structural: templates address inputs by key
    (``{{ rule.inputs_by_key["de.ordinary.gross_wages"].value }}``) so
    declaration order in ``input_fact_keys`` is no longer load-bearing for
    the rendered narrative. This test scans every ``.jinja`` file under
    ``tax_pipeline/narrative/templates/`` and rejects any
    ``rule.inputs[<int>]`` occurrence.

    Authority: docs/invariant-migration-plan.md §7 WS-5G (invariant I12).
    """

    def test_no_positional_input_indexing_in_jinja_templates(self) -> None:
        offenders: list[str] = []
        # Recurse via rglob so a future ``templates/<jurisdiction>/`` subtree
        # is automatically scanned. Today the templates dir is flat but
        # this future-proofs the detector for nested layouts.
        for template_path in sorted(TEMPLATES_DIR.rglob("*.jinja")):
            text = template_path.read_text(encoding="utf-8")
            if PRAGMA_ALLOWLIST in text:
                # The template explicitly opts out; the comment is the
                # documentation. WS-5G expects this list to stay empty.
                continue
            rel = template_path.relative_to(REPO_ROOT)

            # Direct positional access: ``rule.inputs[<int>]``.
            for match in POSITIONAL_INPUT_PATTERN.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(
                    f"{rel}:{line_no}: {match.group(0)} "
                    "(use rule.inputs_by_key[<key>])"
                )

            # Indirect positional access via Jinja ``{% set xs = rule.inputs %}``
            # then ``xs[<int>]``. Any local name aliased to rule.inputs is
            # tainted; subsequent ``<name>[<int>]`` lookup is positional.
            local_aliases: set[str] = set()
            for match in POSITIONAL_VIA_LOCAL_SET_PATTERN.finditer(text):
                local_aliases.add(match.group(1))
            for alias in local_aliases:
                alias_pattern = re.compile(
                    r"\b" + re.escape(alias) + r"\[\s*\d+\s*\]"
                )
                for match in alias_pattern.finditer(text):
                    line_no = text[: match.start()].count("\n") + 1
                    offenders.append(
                        f"{rel}:{line_no}: {match.group(0)} "
                        f"(local alias {alias!r} of rule.inputs is "
                        "still positional; use rule.inputs_by_key[<key>])"
                    )

            # Jinja filter forms: ``rule.inputs|first``, ``|last``, ``|nth(N)``.
            for match in JINJA_POSITIONAL_FILTER_PATTERN.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(
                    f"{rel}:{line_no}: {match.group(0)} "
                    "(use rule.inputs_by_key[<key>])"
                )
        self.assertEqual(
            offenders,
            [],
            "Found positional rule.inputs access in narrative templates. "
            "Per invariant I12 (docs/invariant-migration-plan.md §7 WS-5G), "
            "templates must address inputs by declared fact key: replace "
            '``rule.inputs[N].value`` (and ``xs[N]`` aliases / ``|first`` / '
            '``|last`` / ``|nth(N)`` filter forms) with '
            '``rule.inputs_by_key["<fact.key>"].value`` (look up the key in '
            "the corresponding stage's ``input_fact_keys`` tuple in "
            "``tax_pipeline/{germany,usa,treaty}_2025_stages.py``).\n"
            "Offenders:\n  " + "\n  ".join(offenders),
        )


class PositionalInputPatternUnitTest(unittest.TestCase):
    """Unit tests for the I12 detector regexes. Without these, a
    regression in a sub-pattern would silently pass the integration
    test (which only asserts "no offenders" on the real templates).
    """

    def test_direct_index_caught(self) -> None:
        self.assertTrue(POSITIONAL_INPUT_PATTERN.search("{{ rule.inputs[2].value }}"))

    def test_direct_index_with_whitespace_caught(self) -> None:
        self.assertTrue(POSITIONAL_INPUT_PATTERN.search("{{ rule.inputs[ 0 ] }}"))

    def test_local_alias_set_caught(self) -> None:
        snippet = "{% set xs = rule.inputs %}{{ xs[2].value }}"
        match = POSITIONAL_VIA_LOCAL_SET_PATTERN.search(snippet)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "xs")

    def test_first_filter_caught(self) -> None:
        self.assertTrue(
            JINJA_POSITIONAL_FILTER_PATTERN.search("{{ rule.inputs|first }}")
        )

    def test_last_filter_caught(self) -> None:
        self.assertTrue(
            JINJA_POSITIONAL_FILTER_PATTERN.search("{{ rule.inputs|last }}")
        )

    def test_nth_filter_caught(self) -> None:
        self.assertTrue(
            JINJA_POSITIONAL_FILTER_PATTERN.search("{{ rule.inputs|nth(2) }}")
        )

    def test_keyed_access_not_caught_by_any_pattern(self) -> None:
        snippet = '{{ rule.inputs_by_key["de.ordinary.gross_wages"].value }}'
        self.assertIsNone(POSITIONAL_INPUT_PATTERN.search(snippet))
        self.assertIsNone(POSITIONAL_VIA_LOCAL_SET_PATTERN.search(snippet))
        self.assertIsNone(JINJA_POSITIONAL_FILTER_PATTERN.search(snippet))


if __name__ == "__main__":
    unittest.main()
