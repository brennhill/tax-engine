from __future__ import annotations

import csv
import io
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.forms.common import markdown_heading, markdown_link, markdown_table, required_csv_rows, required_text


@dataclass(frozen=True)
class MatrixColumn:
    header: str
    source_key: str


@dataclass(frozen=True)
class LegalAuditSpec:
    package_title: str
    assumptions_title: str
    assumptions_source_name: str
    trace_index_title: str
    law_matrix_title: str
    source_trace_name: str
    result_line_builder: Callable[[dict], str]
    required_manual_positions_heading: str
    assumptions_required_columns: Sequence[str]
    assumptions_required_nonblank_columns: Sequence[str]
    trace_value_column: str
    trace_value_header: str
    trace_note_column: str
    trace_required_columns: Sequence[str]
    trace_required_nonblank_columns: Sequence[str]
    law_matrix_columns: Sequence[MatrixColumn]
    source_lines: Sequence[str]


def _required_bullet_section(markdown_text: str, section_heading: str) -> list[str]:
    lines = markdown_text.splitlines()
    capture = False
    found_heading = False
    bullets: list[str] = []
    target = section_heading.strip()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if capture:
                break
            capture = stripped == f"## {target}"
            found_heading = found_heading or capture
            continue
        if not capture:
            continue
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    if not found_heading:
        raise ValueError(f"Missing required audit section heading: {section_heading}")
    if not bullets:
        raise ValueError(f"Required audit section has no bullet items: {section_heading}")
    return bullets


def _normalized_markdown(markdown_text: str) -> str:
    return markdown_text.rstrip() + "\n"


def render_law_matrix_csv(headers: list[str], rows: list[dict[str, str]]) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def render_law_matrix_markdown(
    *,
    title: str,
    intro_lines: list[str],
    headers: list[str],
    rows: list[dict[str, str]],
    notes: list[str] | None = None,
) -> str:
    table_headers = tuple(headers)
    table_rows = [[row[header] for header in headers] for row in rows]
    sections: list[str] = [markdown_heading(title), ""]
    sections.extend(f"- {line}" for line in intro_lines)
    sections.extend(["", markdown_table(table_headers, table_rows)])
    if notes:
        sections.extend(["", markdown_heading("Notes", level=2)])
        sections.extend(f"- {line}" for line in notes)
    return "\n".join(sections).rstrip() + "\n"


def render_assumptions_markdown(
    *,
    title: str,
    csv_rows: list[dict[str, str]],
    extra_bullets: list[str],
) -> str:
    sections: list[str] = [markdown_heading(title)]
    if csv_rows:
        sections.extend(
            [
                "",
                markdown_heading("Structured Assumptions", level=2),
                markdown_table(
                    ("Section", "Key", "Value", "Source", "Note"),
                    [
                        (
                            row["section"],
                            row["key"],
                            row["value"],
                            row["source"],
                            row["note"],
                        )
                        for row in csv_rows
                    ],
                ),
            ]
        )
    if extra_bullets:
        sections.extend(["", markdown_heading("Additional Explicit Manual Positions", level=2)])
        sections.extend(f"- {bullet}" for bullet in extra_bullets)
    return "\n".join(sections).rstrip() + "\n"


def render_trace_index_markdown(
    *,
    title: str,
    value_column: str,
    value_header: str,
    rows: list[dict[str, str]],
    source_trace_name: str,
    note_column: str,
) -> str:
    sections: list[str] = [
        markdown_heading(title),
        "",
        f"- This file preserves the legal execution order from `{source_trace_name}`.",
        "- Use it with the law matrix to walk each final number back to its authority and source trace step.",
        "",
        markdown_table(
            ("Order", "Step", value_header, "Note"),
            [
                (str(index), row["step"], row[value_column], row[note_column])
                for index, row in enumerate(rows, start=1)
            ],
        ),
    ]
    return "\n".join(sections).rstrip() + "\n"


def render_index_markdown(
    *,
    title: str,
    final_result_line: str,
    package_lines: list[str],
    source_lines: list[str],
) -> str:
    sections: list[str] = [
        markdown_heading(title),
        "",
        final_result_line,
        "",
        markdown_heading("Package Files", level=2),
    ]
    sections.extend(f"- {line}" for line in package_lines)
    sections.extend(["", markdown_heading("Canonical Sources", level=2)])
    sections.extend(f"- {line}" for line in source_lines)
    return "\n".join(sections).rstrip() + "\n"


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    return required_csv_rows(path)


def load_text(path: Path) -> str:
    return required_text(path)


def validate_required_columns(rows: list[dict[str, str]], required_columns: Sequence[str], *, label: str) -> None:
    if not rows:
        raise FileNotFoundError(f"Missing required rows for {label}")
    missing = [column for column in required_columns if column not in rows[0]]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"Missing required columns for {label}: {missing_list}")


def validate_required_nonblank_values(rows: list[dict[str, str]], required_columns: Sequence[str], *, label: str) -> None:
    missing: list[str] = []
    for index, row in enumerate(rows, start=1):
        for column in required_columns:
            if not str(row.get(column, "")).strip():
                missing.append(f"row {index}:{column}")
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"Missing required values for {label}: {missing_list}")


def _write_package_atomically(root: Path, rendered_files: dict[str, str]) -> None:
    """Atomically replace the legal-audit package directory at ``root``.

    The legal-audit package is a directory of related Markdown / CSV
    artifacts (``overview.md``, ``law-matrix.csv``, ``law-matrix.md``,
    ``assumptions.md``, ``trace-index.md``, ``index.md``) that must
    move from one consistent state to the next as a group — a
    downstream auditor reading the package mid-write would otherwise
    see one new file paired with the previous run's siblings.

    Pattern (mirrors the I9 contract enforced for the final-legal-output
    triple — see ``tax_pipeline/core/io.atomic_write_text`` and
    ``tests/y_agnostic/test_final_legal_output_atomic.py``):

    1. Allocate a unique staging directory in ``root.parent`` via
       ``tempfile.mkdtemp``. The previous code used a fixed
       ``.<name>.staging`` filename, which is exactly the H9
       collision-class bug invariant I9 was added to defend against:
       two concurrent writers would race on the same staging path,
       and the second writer's ``shutil.rmtree`` could destroy the
       first writer's in-flight artifact tree.
    2. Write each file inside the staging directory via
       ``atomic_write_text`` so each file is itself fully written or
       not at all (and inherits the unique-tempfile + ``fsync`` +
       ``os.replace`` durability contract from ``core.io``).
    3. ``os.fsync`` the staging directory itself so its directory
       entries are durable before we rename it onto ``root``.
    4. If ``root`` already exists, move it aside to a unique backup
       directory (also via ``tempfile.mkdtemp``), then rename the
       staging directory onto ``root``. On any failure mid-rename,
       attempt to restore the backup.
    5. ``os.fsync`` ``root.parent`` so the rename itself is durable
       across power loss. On platforms where opening a directory
       for reading isn't supported (Windows), the parent fsync is a
       graceful no-op.

    A crash or exception leaves at most an orphaned staging or backup
    directory in ``root.parent``; readers never see a half-written
    package directory.
    """
    root.parent.mkdir(parents=True, exist_ok=True)
    # Unique staging directory per writer prevents the H9 race where two
    # concurrent writers share a fixed ``.<name>.staging`` path. The
    # ``tempfile.mkdtemp`` call returns a securely-named directory that
    # no other process will reuse.
    staging_root = Path(tempfile.mkdtemp(prefix=f".{root.name}.", suffix=".staging", dir=root.parent))
    backup_root: Path | None = None
    try:
        for name, content in rendered_files.items():
            atomic_write_text(staging_root / name, content)
        # fsync the staging directory's directory entries before any
        # rename so the contents are durable before they become visible
        # under the public name.
        _fsync_directory(staging_root)

        if root.exists():
            backup_root = Path(
                tempfile.mkdtemp(prefix=f".{root.name}.", suffix=".backup", dir=root.parent)
            )
            # ``mkdtemp`` already created an empty directory, but
            # ``os.rename`` requires the destination not to exist on
            # POSIX. Remove the placeholder before the rename.
            backup_root.rmdir()
            os.rename(root, backup_root)
        try:
            os.rename(staging_root, root)
        except BaseException:
            # If the rename fails after we moved the previous package
            # aside, restore the backup so readers don't see a missing
            # ``root``.
            if backup_root is not None and backup_root.exists() and not root.exists():
                os.rename(backup_root, root)
                backup_root = None
            raise
        # Durable rename: fsync the parent so the directory-entry
        # update (the ``root`` rename) is on stable storage. Mirrors
        # the parent-fsync step in ``core.io.atomic_write_text``.
        _fsync_directory(root.parent)
    except BaseException:
        # Best-effort cleanup of the staging directory on any failure
        # path that didn't already consume it via ``os.rename``.
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        raise
    else:
        if backup_root is not None and backup_root.exists():
            shutil.rmtree(backup_root, ignore_errors=True)


def _fsync_directory(path: Path) -> None:
    """Best-effort fsync of a directory's metadata for durable renames.

    No-op on platforms (e.g., Windows) where ``os.O_RDONLY`` on a
    directory isn't supported, or filesystems (some network mounts)
    that refuse directory fsync. Mirrors the parent-fsync handling in
    ``core.io.atomic_write_text``.
    """
    try:
        dir_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def render_legal_audit_package(
    *,
    root: Path,
    results: dict,
    overview_text: str,
    trace_rows: list[dict[str, str]],
    assumption_rows: list[dict[str, str]],
    spec: LegalAuditSpec,
) -> None:
    validate_required_columns(trace_rows, spec.trace_required_columns, label=spec.source_trace_name)
    validate_required_nonblank_values(
        trace_rows,
        spec.trace_required_nonblank_columns,
        label=spec.source_trace_name,
    )
    validate_required_columns(
        assumption_rows,
        spec.assumptions_required_columns,
        label=spec.assumptions_source_name,
    )
    validate_required_nonblank_values(
        assumption_rows,
        spec.assumptions_required_nonblank_columns,
        label=spec.assumptions_source_name,
    )
    extra_manual_positions = _required_bullet_section(overview_text, spec.required_manual_positions_heading)

    law_matrix_rows = [
        {column.header: row[column.source_key] for column in spec.law_matrix_columns}
        for row in trace_rows
    ]
    law_headers = [column.header for column in spec.law_matrix_columns]
    rendered_files = {
        "overview.md": _normalized_markdown(overview_text),
        "law-matrix.csv": render_law_matrix_csv(law_headers, law_matrix_rows),
        "law-matrix.md": render_law_matrix_markdown(
            title=spec.law_matrix_title,
            intro_lines=[
                "This matrix maps each trace step to the cited statute or official authority.",
                "It is generated from the canonical tax trace and does not recompute tax.",
            ],
            headers=law_headers,
            rows=law_matrix_rows,
            notes=[
                "Use `trace-index.md` to preserve execution order and displayed values.",
                "Use `overview.md` for the narrative legal-order explanation.",
            ],
        ),
        "assumptions.md": render_assumptions_markdown(
            title=spec.assumptions_title,
            csv_rows=assumption_rows,
            extra_bullets=extra_manual_positions,
        ),
        "trace-index.md": render_trace_index_markdown(
            title=spec.trace_index_title,
            value_column=spec.trace_value_column,
            value_header=spec.trace_value_header,
            rows=trace_rows,
            source_trace_name=spec.source_trace_name,
            note_column=spec.trace_note_column,
        ),
        "index.md": render_index_markdown(
            title=spec.package_title,
            final_result_line=spec.result_line_builder(results),
            package_lines=[
                markdown_link("overview.md", "overview.md"),
                markdown_link("law-matrix.csv", "law-matrix.csv"),
                markdown_link("law-matrix.md", "law-matrix.md"),
                markdown_link("assumptions.md", "assumptions.md"),
                markdown_link("trace-index.md", "trace-index.md"),
            ],
            source_lines=list(spec.source_lines),
        ),
    }
    _write_package_atomically(root, rendered_files)
