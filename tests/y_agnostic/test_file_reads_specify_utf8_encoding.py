"""Invariant I10: every file read/write in ``tax_pipeline/`` pins ``encoding="utf-8"``.

Per the project CLAUDE.md determinism principle:

    If a legal source is unclear, year-specific, conflicting, missing, or
    not yet modeled, fail closed with an explicit error or `not_applicable`;
    never silently default to zero.

The same fail-closed discipline applies to file I/O. A pipeline that reads
a CSV or JSON file without specifying ``encoding="utf-8"`` quietly inherits
the platform locale (``cp1252`` on Windows, ``UTF-8`` on macOS/Linux). That
non-determinism corrupts German umlauts and EUR symbols in CSVs, makes
fingerprint payloads platform-dependent, and undermines audit-packet
reproducibility. The 2026-05-01 correctness review L-encoding finding
documented this risk for the engine.

This test AST-scans every ``.py`` file under ``tax_pipeline/`` and flags:

* ``<path>.read_text(...)`` / ``<path>.write_text(...)`` without ``encoding=``.
* Builtin ``open(path, ...)`` and ``<path>.open(...)`` (Path.open) without
  ``encoding=`` when the mode is text (no ``b`` flag, default text mode).
* ``csv.DictReader(open(...))`` and ``csv.reader(open(...))`` patterns where
  the inner ``open`` lacks ``encoding=``.

Binary call sites (mode contains ``b``) are skipped — those legitimately
do not use a text encoding. Annotate edge cases with a trailing
``# pragma: encoding-ok <reason>`` to exempt that line.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PIPELINE_DIR = REPO_ROOT / "tax_pipeline"
ALLOW_PRAGMA = "# pragma: encoding-ok"


def _has_kwarg(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _is_open_call(func: ast.AST) -> bool:
    if isinstance(func, ast.Name) and func.id == "open":
        return True
    if not (isinstance(func, ast.Attribute) and func.attr == "open"):
        return False
    if isinstance(func.value, ast.Name) and func.value.id == "os":
        return False
    return True


def _mode_string(call: ast.Call) -> str | None:
    """Return the literal mode string passed to open()/Path.open(), or None.

    Mode is the second positional arg for builtin ``open`` and the first for
    ``Path.open``. Default is text ``"r"``."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        idx = 1
    elif isinstance(func, ast.Attribute) and func.attr == "open":
        idx = 0
    else:
        return None
    if len(call.args) > idx and isinstance(call.args[idx], ast.Constant):
        value = call.args[idx].value
        return value if isinstance(value, str) else None
    return ""  # default "r"


class FileEncodingVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.offenders: list[tuple[int, str]] = []

    def _flag(self, lineno: int, message: str) -> None:
        line = self.source_lines[lineno - 1] if 1 <= lineno <= len(self.source_lines) else ""
        if ALLOW_PRAGMA in line:
            return
        self.offenders.append((lineno, message))

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast API
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"read_text", "write_text"}:
            if not _has_kwarg(node, "encoding"):
                self._flag(node.lineno, f".{func.attr}(...) missing encoding=")
        elif _is_open_call(func):
            mode = _mode_string(node)
            if mode is not None and "b" not in mode and not _has_kwarg(node, "encoding"):
                label = "open(...)" if isinstance(func, ast.Name) else ".open(...)"
                self._flag(node.lineno, f"{label} text-mode missing encoding=")
        if isinstance(func, ast.Attribute) and func.attr in {"DictReader", "reader"}:
            if node.args and isinstance(node.args[0], ast.Call):
                inner = node.args[0]
                if _is_open_call(inner.func):
                    mode = _mode_string(inner)
                    if mode is not None and "b" not in mode and not _has_kwarg(inner, "encoding"):
                        self._flag(inner.lineno, f"csv.{func.attr}(open(...)) missing encoding=")
        self.generic_visit(node)


class FileReadsSpecifyUtf8EncodingTest(unittest.TestCase):
    def test_every_file_io_call_pins_utf8_encoding(self) -> None:
        offenders: list[str] = []
        for py_path in sorted(TAX_PIPELINE_DIR.rglob("*.py")):
            source = py_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_path))
            visitor = FileEncodingVisitor(source.splitlines())
            visitor.visit(tree)
            for lineno, message in visitor.offenders:
                rel = py_path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{lineno}: {message}")
        self.assertFalse(
            offenders,
            "File I/O sites missing encoding=\"utf-8\" (CLAUDE.md determinism, "
            "I10). Add encoding=\"utf-8\" or annotate with "
            "'# pragma: encoding-ok <reason>':\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
