"""Shared I/O primitives for the tax pipeline.

This module hosts helpers that multiple pipeline modules need to share
across package boundaries:

- :func:`atomic_write_text` — durable, race-free text writer used by the
  final-legal-output triple (``final-legal-output.json``,
  ``legal-execution-graph.json``, ``legal-execution-graph.mmd``), the
  derivation-pipeline artifacts (``derived-facts.json``,
  ``derivation-graph.json``), and any other code path that has to commit
  a JSON / Markdown artifact without leaving torn or stale state on disk
  for downstream readers (form renderers, the audit packet writer).
- :class:`AuditEncoder` — JSON encoder that handles the non-JSON-native
  types flowing through the rule graph (Decimals, dataclasses,
  sets/frozensets) so persisted artifacts canonicalize identically
  regardless of which pipeline stage produced them.

These were previously private helpers (``_atomic_write_text`` in
``pipelines.y2025.final_legal_output``, ``_AuditEncoder`` in
``pipelines.y2025.rule_narrative_packets``). They were imported across
module boundaries by name, which broke the leading-underscore "private
to this module" convention. Promoting them to a public ``core`` module
keeps the audit-write contract in one canonical, importable location
(invariant I9 — atomic writes use unique temp filenames + parent fsync —
is enforced by ``tests/y_agnostic/test_final_legal_output_atomic.py``).
"""
from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically.

    Allocates a unique temp file in the target's parent directory via
    ``tempfile.NamedTemporaryFile`` (so concurrent writers never collide
    on a fixed ``.<name>.tmp`` filename), ``fsync()``s the file's
    descriptor before rename, ``os.replace()``s the temp file onto the
    target, then ``fsync()``s the parent directory descriptor on POSIX
    so the rename itself is durable across power loss. On Windows
    (where ``os.O_RDONLY`` on a directory is not generally supported)
    the parent fsync is a graceful no-op.

    A crash or exception between writes leaves at most an orphaned
    temp file (which we attempt to clean up in the error path);
    readers never see a half-written or empty target file.

    Required for the final-legal-output triple
    (``final-legal-output.json``, ``legal-execution-graph.json``,
    ``legal-execution-graph.mmd``) and the derivation artifacts so a
    partial failure cannot leave a downstream form renderer reading a
    stale or inconsistent set.

    Closes audit finding H9 (atomic-write filename collision) — see
    ``docs/invariant-migration-plan.md`` §4 WS-2E. Enforced by invariant
    I9 (``tests/y_agnostic/test_final_legal_output_atomic.py``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp filename per writer prevents the H9 race where two
    # concurrent writers share ``.<name>.tmp``: writer A's open() truncates
    # writer B's in-flight bytes, then A's os.replace clobbers B's,
    # leaving B's content lost and possibly leaving a stale half-written
    # temp on disk.
    tmp_handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_name = tmp_handle.name
    try:
        try:
            tmp_handle.write(text)
            tmp_handle.flush()
            os.fsync(tmp_handle.fileno())
        finally:
            tmp_handle.close()
        os.replace(tmp_name, path)
    except BaseException:
        # Best-effort cleanup of the orphan temp file. Swallow OSError
        # (e.g., file already moved by os.replace, or directory gone)
        # so the original exception propagates unchanged.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    # Durable rename: on POSIX, the directory entry update from
    # os.replace is not guaranteed to be on stable storage until the
    # parent directory itself is fsync'd. On Windows, opening a
    # directory for reading isn't supported the same way, so we
    # gracefully no-op on any OSError here.
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        # Some filesystems (e.g., certain network mounts) refuse
        # directory fsync. The replace itself is already atomic at the
        # VFS level; missing the durability barrier is acceptable.
        pass
    finally:
        os.close(dir_fd)


class AuditEncoder(json.JSONEncoder):
    """JSON encoder for narrative-packet input/output values.

    Handles the non-JSON-native types that flow through the rule graph:
    Decimals (formatted as fixed-point strings), dataclass instances
    (converted to plain dicts), and sets/frozensets (sorted to a stable
    list). Everything else falls through to the standard encoder.
    """

    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return format(o, "f")
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if isinstance(o, (frozenset, set)):
            return sorted(o, key=str)
        return super().default(o)


__all__ = [
    "AuditEncoder",
    "atomic_write_text",
]
