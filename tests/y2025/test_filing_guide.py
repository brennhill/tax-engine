"""Tests for the per-jurisdiction filing-guide renderer.

Authority anchors and structural-invariant guards:

- CLAUDE.md invariant **I3** — the filing guide is a meta-renderer that
  re-presents existing form Markdown; it must NOT introduce new
  ``OutputDeclaration.form_line_refs``. The test suite asserts the
  module does not call any of the form-line write helpers.
- CLAUDE.md invariant **I5** — no Decimal arithmetic in the renderer.
  Asserted via an AST scan of ``forms/filing_guide.py``.
- CLAUDE.md invariant **I13** — when
  ``elections.us_filing_required=false`` the U.S. ``FILING-GUIDE.md``
  must not be rendered. Asserted by running the pipeline against the
  ``de-only-demo-2025`` workspace.
"""

from __future__ import annotations

import ast
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.forms.filing_guide import (
    GERMANY_FORMS,
    USA_FORMS,
    FormSpec,
    _topological_sort,
    parse_lines_table,
    parse_title,
    render_germany_filing_guide,
    render_usa_filing_guide,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.run_year import run_year


class TopologicalSortTest(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(_topological_sort([]), [])

    def test_dependency_order_holds(self) -> None:
        a = FormSpec("a.md", "A", "for a", "trigger", feeds_into=("c.md",))
        b = FormSpec("b.md", "B", "for b", "trigger", feeds_into=("c.md",))
        c = FormSpec("c.md", "C", "for c", "trigger", role="main_return")
        ordered = _topological_sort([c, a, b])
        names = [f.basename for f in ordered]
        self.assertEqual(names, ["a.md", "b.md", "c.md"])

    def test_main_return_always_last(self) -> None:
        # Even when a main-return form has no incoming edges, role-based
        # priority should push it to the end.
        main = FormSpec("main.md", "Main", "for main", "trigger", role="main_return")
        helper = FormSpec("helper.md", "Helper", "for helper", "trigger")
        ordered = _topological_sort([main, helper])
        self.assertEqual([f.basename for f in ordered], ["helper.md", "main.md"])

    def test_standalone_after_functional_before_main_return(self) -> None:
        functional = FormSpec("func.md", "Func", "for func", "trigger", feeds_into=("main.md",))
        standalone = FormSpec("disc.md", "Disclosure", "for disc", "trigger", role="standalone")
        main = FormSpec("main.md", "Main", "for main", "trigger", role="main_return")
        ordered = _topological_sort([standalone, main, functional])
        self.assertEqual([f.basename for f in ordered], ["func.md", "disc.md", "main.md"])

    def test_usa_catalog_topo_order_terminates_in_form_1040(self) -> None:
        ordered = _topological_sort(USA_FORMS)
        self.assertEqual(ordered[-1].basename, "2025_1040.md")
        # Every functional form's downstream consumer comes after it.
        for index, form in enumerate(ordered):
            for downstream in form.feeds_into:
                downstream_index = next(
                    (i for i, f in enumerate(ordered) if f.basename == downstream),
                    None,
                )
                if downstream_index is not None:
                    self.assertGreater(
                        downstream_index,
                        index,
                        f"{form.basename} must come BEFORE its downstream {downstream}",
                    )

    def test_germany_catalog_topo_order_terminates_in_hauptvordruck(self) -> None:
        ordered = _topological_sort(GERMANY_FORMS)
        self.assertEqual(ordered[-1].basename, "2025_hauptvordruck.md")


class LinesTableParserTest(unittest.TestCase):
    def test_extracts_rows_in_order(self) -> None:
        md = (
            "# 2025 Form X\n"
            "\n"
            "## Lines\n"
            "| Line | Value | Source | Notes |\n"
            "| --- | --- | --- | --- |\n"
            "| Line 1 | 100.00 USD | src.json | Note one |\n"
            "| Line 2 | 200.00 USD | src.json |  |\n"
            "\n"
            "## Notes\n"
        )
        rows = parse_lines_table(md)
        self.assertEqual(rows[0], ("Line 1", "100.00 USD", "src.json", "Note one"))
        self.assertEqual(rows[1], ("Line 2", "200.00 USD", "src.json", ""))

    def test_empty_when_no_lines_table(self) -> None:
        self.assertEqual(parse_lines_table("# title\n\n## Notes\n- ..."), [])

    def test_parse_title(self) -> None:
        self.assertEqual(parse_title("# Hello\n\n## body"), "Hello")
        self.assertIsNone(parse_title("no heading here"))


class FilingGuideRenderingTest(unittest.TestCase):
    """End-to-end render against the demo workspace.

    Authority: 26 U.S.C. § 6012 (CLAUDE.md invariant I13) — the U.S.
    guide is gated on ``elections.us_filing_required=true``.
    """

    def _run_demo(self, demo_name: str) -> YearPaths:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        paths = materialize_demo_workspace(root, demo_name=demo_name, year=2025)
        with redirect_stdout(io.StringIO()):
            run_year(root, "2025", workspace_root=paths.year_root)
        return paths

    def test_demo_renders_both_guides_with_section_headings(self) -> None:
        paths = self._run_demo("demo-2025")
        us_guide = paths.usa_forms_root / "FILING-GUIDE.md"
        de_guide = paths.germany_forms_root / "FILING-GUIDE.md"
        self.assertTrue(us_guide.exists(), "U.S. FILING-GUIDE.md must be rendered")
        self.assertTrue(de_guide.exists(), "Germany FILING-GUIDE.md must be rendered")

        us_text = us_guide.read_text(encoding="utf-8")
        de_text = de_guide.read_text(encoding="utf-8")
        for needle in (
            "## Section A — Form filing order",
            "## Section B — Per-form fill-in checklist",
        ):
            self.assertIn(needle, us_text, f"U.S. guide missing: {needle}")
            self.assertIn(needle, de_text, f"DE guide missing: {needle}")

    def test_demo_us_guide_has_form_1040_last_step_with_transfers(self) -> None:
        paths = self._run_demo("demo-2025")
        us_text = (paths.usa_forms_root / "FILING-GUIDE.md").read_text(encoding="utf-8")
        # The last numeric step in Section A must be Form 1040.
        section_a = us_text.split("## Section B")[0]
        step_headings = [
            line for line in section_a.splitlines() if line.startswith("### Step ")
        ]
        self.assertGreater(len(step_headings), 0)
        self.assertIn("Form 1040", step_headings[-1])
        # Cross-form transfer annotation visible somewhere in Section B.
        section_b = us_text.split("## Section B")[1]
        self.assertIn("→ Schedule D Line", section_b)

    def test_demo_de_guide_has_hauptvordruck_last_step(self) -> None:
        paths = self._run_demo("demo-2025")
        de_text = (paths.germany_forms_root / "FILING-GUIDE.md").read_text(encoding="utf-8")
        section_a = de_text.split("## Section B")[0]
        step_headings = [
            line for line in section_a.splitlines() if line.startswith("### Step ")
        ]
        self.assertGreater(len(step_headings), 0)
        self.assertIn("Hauptvordruck", step_headings[-1])

    def test_index_links_filing_guide_first(self) -> None:
        paths = self._run_demo("demo-2025")
        for forms_root in (paths.usa_forms_root, paths.germany_forms_root):
            text = (forms_root / "index.md").read_text(encoding="utf-8")
            self.assertIn("FILING-GUIDE.md", text)
            self.assertIn("Start here", text)

    def test_us_guide_absent_when_us_filing_not_required(self) -> None:
        # CLAUDE.md invariant I13: the de-only-demo-2025 workspace has
        # ``elections.us_filing_required=false`` (26 U.S.C. § 6012). The
        # U.S. side — including the U.S. FILING-GUIDE.md — must not be
        # rendered.
        paths = self._run_demo("de-only-demo-2025")
        us_guide = paths.usa_forms_root / "FILING-GUIDE.md"
        self.assertFalse(
            us_guide.exists(),
            "U.S. FILING-GUIDE.md must not be rendered when us_filing_required=false",
        )
        # The Germany guide still renders.
        self.assertTrue(
            (paths.germany_forms_root / "FILING-GUIDE.md").exists(),
            "Germany FILING-GUIDE.md must still render under DE-only posture",
        )


class FilingGuideStructuralInvariantsTest(unittest.TestCase):
    """Static guards on the filing-guide source.

    These keep the meta-renderer aligned with CLAUDE.md invariants
    I3 (no new form-line writes) and I5 (no Decimal arithmetic).
    """

    SOURCE_PATH = Path(__file__).resolve().parents[2] / "tax_pipeline" / "forms" / "filing_guide.py"

    def test_no_decimal_arithmetic_in_filing_guide_source(self) -> None:
        # I5: the guide is a re-presentation. Display values are pulled
        # verbatim from already-rendered Markdown. No Decimal math, no
        # imports of Decimal at all.
        source = self.SOURCE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "decimal":
                self.fail(
                    "filing_guide.py must not import from `decimal`; "
                    "values come from already-rendered form Markdown."
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name,
                        "decimal",
                        "filing_guide.py must not import `decimal`",
                    )

    def test_filing_guide_does_not_call_form_line_writers(self) -> None:
        # I3: re-presentation only — must not call legal_value_entry,
        # legal_value_from_dict, legal_value_from_decimal, or write_form.
        source = self.SOURCE_PATH.read_text(encoding="utf-8")
        forbidden = {
            "legal_value_entry",
            "legal_value_from_dict",
            "legal_value_from_decimal",
            "write_form",
            "FormEntry",
        }
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = None
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name in forbidden:
                    self.fail(
                        f"filing_guide.py must not call {func_name!r}; "
                        "the guide is a re-presentation of already-rendered form lines."
                    )


if __name__ == "__main__":
    unittest.main()
