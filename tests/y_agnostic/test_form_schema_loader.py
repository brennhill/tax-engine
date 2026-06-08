"""Unit tests for :mod:`tax_pipeline.forms._schema` (Y2 / P5 loader).

Covers:

- Loader returns parsed schema with declared lines.
- ``find_line`` raises KeyError for unknown ``line_id``.
- ``label(line_id)`` returns the rendered string.
- Required fields fail closed (missing / wrong type).
- Duplicate ``line_id`` is rejected.
- ``unused = true`` requires a non-empty ``reason``.
- ``form_id`` must match the filename stem.

The tests write throw-away schemas to a tmp dir; no production schema
files are mutated. The loader's ``_SCHEMAS_ROOT`` is monkey-patched
per-test to point at the tmp dir.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tax_pipeline.forms import _schema as form_schema


_VALID_TOML = """\
form_id = "test_form"
form_year = 2025
display_name = "Test Form"
authority_url = "https://example.test/about-test"
canonical_form_name = "Test Form"

[[lines]]
line_id = "1"
label = "Line 1"

[[lines]]
line_id = "2a"
label = "Line 2a"

[[lines]]
line_id = "diagnostic_only"
label = "Diagnostic"
unused = true
reason = "Internal worksheet line; no rule output cites this line."
"""


class FormSchemaLoaderTest(unittest.TestCase):

    def _write_schema(self, contents: str, *, form_id: str = "test_form") -> Path:
        tmp = Path(tempfile.mkdtemp())
        path = tmp / f"{form_id}.toml"
        path.write_text(contents, encoding="utf-8")
        return tmp

    def _patched_root(self, tmp: Path):
        return patch.object(form_schema, "_SCHEMAS_ROOT", tmp)

    def test_loads_valid_schema(self) -> None:
        tmp = self._write_schema(_VALID_TOML)
        with self._patched_root(tmp):
            schema = form_schema.load_form_schema("test_form")
        self.assertEqual(schema.form_id, "test_form")
        self.assertEqual(schema.form_year, 2025)
        self.assertEqual(schema.display_name, "Test Form")
        self.assertEqual(schema.canonical_form_name, "Test Form")
        self.assertEqual(len(schema.lines), 3)
        self.assertEqual(schema.lines[0].line_id, "1")
        self.assertEqual(schema.lines[0].label, "Line 1")
        self.assertFalse(schema.lines[0].unused)
        self.assertTrue(schema.lines[2].unused)
        self.assertEqual(
            schema.lines[2].reason,
            "Internal worksheet line; no rule output cites this line.",
        )

    def test_find_line_returns_matching_entry(self) -> None:
        tmp = self._write_schema(_VALID_TOML)
        with self._patched_root(tmp):
            schema = form_schema.load_form_schema("test_form")
        line = schema.find_line("2a")
        self.assertEqual(line.line_id, "2a")
        self.assertEqual(line.label, "Line 2a")

    def test_find_line_unknown_raises_keyerror(self) -> None:
        tmp = self._write_schema(_VALID_TOML)
        with self._patched_root(tmp):
            schema = form_schema.load_form_schema("test_form")
        with self.assertRaises(KeyError):
            schema.find_line("does_not_exist")

    def test_label_helper(self) -> None:
        tmp = self._write_schema(_VALID_TOML)
        with self._patched_root(tmp):
            schema = form_schema.load_form_schema("test_form")
        self.assertEqual(schema.label("2a"), "Line 2a")

    def test_missing_file_raises_filenotfounderror(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        with self._patched_root(tmp):
            with self.assertRaises(FileNotFoundError):
                form_schema.load_form_schema("missing")

    def test_form_id_mismatch_rejected(self) -> None:
        bad = _VALID_TOML.replace(
            'form_id = "test_form"', 'form_id = "wrong_id"'
        )
        tmp = self._write_schema(bad)
        with self._patched_root(tmp):
            with self.assertRaises(ValueError) as ctx:
                form_schema.load_form_schema("test_form")
        self.assertIn("does not match filename stem", str(ctx.exception))

    def test_missing_required_top_level_field(self) -> None:
        bad = _VALID_TOML.replace(
            'authority_url = "https://example.test/about-test"\n', ""
        )
        tmp = self._write_schema(bad)
        with self._patched_root(tmp):
            with self.assertRaises(ValueError) as ctx:
                form_schema.load_form_schema("test_form")
        self.assertIn("authority_url", str(ctx.exception))

    def test_zero_lines_allowed_for_dynamic_forms(self) -> None:
        # Schemas with no [[lines]] are valid: they describe forms whose
        # Markdown rows come wholly from runtime data (Schedule D /
        # Form 8949). The schema still pins display_name +
        # canonical_form_name + authority_url for title and I3.
        valid = """
form_id = "test_form"
form_year = 2025
display_name = "Test Form"
authority_url = "https://example.test/about-test"
canonical_form_name = "Test Form"
"""
        tmp = self._write_schema(valid)
        with self._patched_root(tmp):
            schema = form_schema.load_form_schema("test_form")
        self.assertEqual(schema.lines, ())

    def test_duplicate_line_id_rejected(self) -> None:
        bad = _VALID_TOML + """
[[lines]]
line_id = "1"
label = "Duplicate"
"""
        tmp = self._write_schema(bad)
        with self._patched_root(tmp):
            with self.assertRaises(ValueError) as ctx:
                form_schema.load_form_schema("test_form")
        self.assertIn("duplicate line_id", str(ctx.exception))

    def test_unused_without_reason_rejected(self) -> None:
        bad = """
form_id = "test_form"
form_year = 2025
display_name = "Test Form"
authority_url = "https://example.test/about-test"
canonical_form_name = "Test Form"

[[lines]]
line_id = "x"
label = "Unused without reason"
unused = true
"""
        tmp = self._write_schema(bad)
        with self._patched_root(tmp):
            with self.assertRaises(ValueError) as ctx:
                form_schema.load_form_schema("test_form")
        self.assertIn("reason", str(ctx.exception))

    def test_unused_default_is_false(self) -> None:
        tmp = self._write_schema(_VALID_TOML)
        with self._patched_root(tmp):
            schema = form_schema.load_form_schema("test_form")
        # First two lines have no unused marker — should default False.
        self.assertFalse(schema.lines[0].unused)
        self.assertFalse(schema.lines[1].unused)

    def test_iter_schema_form_ids_returns_sorted_tuple(self) -> None:
        tmp = self._write_schema(_VALID_TOML, form_id="b_form")
        # Add a second valid schema.
        valid_a = _VALID_TOML.replace(
            'form_id = "test_form"', 'form_id = "a_form"'
        )
        (tmp / "a_form.toml").write_text(valid_a, encoding="utf-8")
        with self._patched_root(tmp):
            ids = form_schema.iter_schema_form_ids()
        self.assertEqual(ids, ("a_form", "b_form"))


if __name__ == "__main__":
    unittest.main()
