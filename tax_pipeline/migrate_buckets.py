"""Proposal 8 (raw-bucket redesign) migration helper.

This CLI converts a workspace from the legacy flat raw layout

    raw/germany/...
    raw/us/...
    raw/brokers/...
    raw/crypto/...
    raw/equity_comp/...
    raw/receipts/...
    raw/real_estate/...

to the new dual-dimension Proposal 8 layout

    raw/jurisdictions/de/...
    raw/jurisdictions/us/...
    raw/asset_classes/brokers/...
    raw/asset_classes/crypto/...
    raw/asset_classes/equity_comp/...
    raw/asset_classes/receipts/...
    raw/asset_classes/real_estate/...

The migration **copies** files (it does not move) so that a
half-migrated workspace can be rolled back by simply discarding the
new directory tree. Once the user is satisfied the new layout is
correct, they can delete the legacy directories manually -- the
runtime keeps reading either layout indefinitely.

Usage::

    tax-pipeline-migrate-buckets <workspace>            # dry-run (default)
    tax-pipeline-migrate-buckets <workspace> --apply    # actually copy
    tax-pipeline-migrate-buckets <workspace> --apply --remove-legacy

The ``--remove-legacy`` flag deletes the old flat directories after a
successful copy. It is opt-in so the default is non-destructive.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from tax_pipeline.paths import (
    ASSET_CLASS_BUCKETS,
    JURISDICTION_LEGACY_NAMES,
    canonical_bucket_path,
)


@dataclass(frozen=True)
class _PlannedCopy:
    """One ``(legacy_path, canonical_path)`` planned move.

    ``relative_path`` is the file's path relative to ``raw/`` in the
    legacy layout; the migration helper logs it verbatim for review.
    """

    relative_path: str
    legacy_source: Path
    canonical_destination: Path


def _legacy_bucket_dirs(raw_root: Path) -> list[tuple[str, Path]]:
    """Return ``[(bucket_name, dir_path)]`` for every legacy flat bucket.

    Includes both jurisdiction legacy names (``germany``, ``us``) and
    asset-class names (``brokers``, ``crypto``, ...). Skips directories
    that do not exist on disk.
    """

    dirs: list[tuple[str, Path]] = []
    for bucket in JURISDICTION_LEGACY_NAMES:
        candidate = raw_root / bucket
        if candidate.is_dir():
            dirs.append((bucket, candidate))
    for bucket in ASSET_CLASS_BUCKETS:
        candidate = raw_root / bucket
        if candidate.is_dir():
            dirs.append((bucket, candidate))
    return dirs


def _files_equal(a: Path, b: Path) -> bool:
    """Byte-equality check used to skip already-copied files.

    A previous ``--apply`` run leaves the legacy file in place
    alongside its canonical copy (the default, non-destructive
    behavior). Re-running ``--apply`` should be a no-op on files
    whose canonical destination already matches the legacy source --
    otherwise the helper would re-copy every file on every
    invocation.
    """

    if not (a.is_file() and b.is_file()):
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    return a.read_bytes() == b.read_bytes()


def plan_migration(raw_root: Path) -> list[_PlannedCopy]:
    """Walk the legacy buckets and build a planned-copy list.

    Hidden files (``.evidence-only/``, ``.intake-uploads.json``) and
    files already at the canonical destination are preserved. Each
    planned copy records the file's relative path so the operator can
    review the move before applying. Files whose canonical
    destination already exists with byte-identical contents are
    skipped so repeated ``--apply`` runs are idempotent.
    """

    plans: list[_PlannedCopy] = []
    for bucket, bucket_dir in _legacy_bucket_dirs(raw_root):
        canonical_root = canonical_bucket_path(raw_root, bucket)
        for source in sorted(p for p in bucket_dir.rglob("*") if p.is_file()):
            relative_under_bucket = source.relative_to(bucket_dir)
            destination = canonical_root / relative_under_bucket
            if destination == source:
                # Nothing to do -- file is already at the canonical
                # location (defensive: this should not happen because
                # the legacy and canonical roots differ for every
                # known bucket).
                continue
            if _files_equal(source, destination):
                # Idempotence: a prior ``--apply`` already produced
                # this canonical copy. Skip so re-running is a no-op.
                continue
            relative_under_raw = source.relative_to(raw_root).as_posix()
            plans.append(
                _PlannedCopy(
                    relative_path=relative_under_raw,
                    legacy_source=source,
                    canonical_destination=destination,
                )
            )
    return plans


def _format_plan_table(plans: list[_PlannedCopy], raw_root: Path) -> str:
    if not plans:
        return "(no files to migrate -- raw/ is already on the canonical layout)"
    lines = ["Planned migrations (legacy -> canonical):"]
    for plan in plans:
        legacy_rel = plan.legacy_source.relative_to(raw_root).as_posix()
        canonical_rel = plan.canonical_destination.relative_to(raw_root).as_posix()
        lines.append(f"  raw/{legacy_rel}  ->  raw/{canonical_rel}")
    return "\n".join(lines)


def apply_migration(
    plans: list[_PlannedCopy],
    *,
    raw_root: Path | None = None,
    remove_legacy: bool = False,
) -> int:
    """Execute the planned copies. Returns the number of files copied.

    ``raw_root`` is required when ``remove_legacy=True`` so the
    function can locate the top-level legacy bucket directories. A
    partial copy leaves the legacy tree intact so the user can re-run
    the helper.

    With ``remove_legacy=True`` and a ``raw_root``, the helper deletes
    every legacy bucket directory whose files were copied to the new
    layout. It also deletes legacy bucket directories that are empty
    (or contain only hidden ``.DS_Store``-style cruft) so a workspace
    that has already been migrated -- or a fresh scaffold whose legacy
    stubs were never populated -- ends up on a clean canonical layout
    after one ``--apply --remove-legacy`` run.
    """

    copied = 0
    for plan in plans:
        plan.canonical_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plan.legacy_source, plan.canonical_destination)
        copied += 1
    if remove_legacy and raw_root is not None:
        for bucket in (*JURISDICTION_LEGACY_NAMES.keys(), *ASSET_CLASS_BUCKETS):
            legacy_top = raw_root / bucket
            if not legacy_top.is_dir():
                continue
            migrated_from_here = any(
                p.legacy_source.is_relative_to(legacy_top) for p in plans
            )
            if migrated_from_here:
                shutil.rmtree(legacy_top)
                continue
            # Idempotence: an empty legacy bucket dir (typical on a
            # workspace that has already been migrated, or a fresh
            # scaffold whose legacy stubs were never populated) is
            # safe to remove. Treat directories whose only contents
            # are hidden-name files (``.DS_Store``) as empty too.
            visible_children = [
                child for child in legacy_top.iterdir() if not child.name.startswith(".")
            ]
            if not visible_children:
                shutil.rmtree(legacy_top)
                continue
            # Two-step migration recovery: a previous ``--apply`` run
            # already copied every file under this bucket to the
            # canonical layout (so ``plan_migration`` returned an empty
            # list this time), but the legacy directory was left in
            # place because ``--remove-legacy`` was not set on that
            # earlier run. If every visible file under ``legacy_top``
            # has a byte-identical twin at its canonical destination,
            # it is safe to remove the legacy tree -- the data already
            # lives in the canonical layout. This restores the user's
            # mental model that ``--apply --remove-legacy`` finishes
            # the migration, regardless of whether they invoked it in
            # one step or two.
            canonical_root = canonical_bucket_path(raw_root, bucket)
            all_have_canonical_twin = True
            for source in (p for p in legacy_top.rglob("*") if p.is_file()):
                if source.name.startswith("."):
                    continue
                relative_under_bucket = source.relative_to(legacy_top)
                destination = canonical_root / relative_under_bucket
                if not _files_equal(source, destination):
                    all_have_canonical_twin = False
                    break
            if all_have_canonical_twin:
                shutil.rmtree(legacy_top)
    return copied


def migrate_workspace(
    workspace: Path,
    *,
    apply: bool = False,
    remove_legacy: bool = False,
    output=sys.stdout,
) -> int:
    """Top-level migration entry point. Returns the number of files copied.

    A ``--dry-run`` (``apply=False``) call returns the number of files
    that *would* be copied so callers can use the count for status
    reporting. A ``--apply`` call performs the copies and (optionally)
    removes the legacy directories.
    """

    raw_root = (workspace / "raw").resolve()
    if not raw_root.is_dir():
        print(f"No raw/ directory at {raw_root}; nothing to migrate.", file=output)
        return 0

    plans = plan_migration(raw_root)
    print(_format_plan_table(plans, raw_root), file=output)
    if not plans and not (apply and remove_legacy):
        # Idempotent fast path: no files to copy and no cleanup
        # requested. ``--apply --remove-legacy`` on an already-clean
        # workspace still falls through so the helper can rmdir empty
        # legacy stubs left behind by a prior scaffold.
        return 0
    if not apply:
        print(
            f"Dry-run: {len(plans)} file(s) would be copied. "
            "Re-run with --apply to migrate.",
            file=output,
        )
        return 0

    copied = apply_migration(plans, raw_root=raw_root, remove_legacy=remove_legacy)
    if copied:
        print(f"Copied {copied} file(s) to the new layout.", file=output)
    if remove_legacy:
        print("Removed legacy bucket directories.", file=output)
    elif copied:
        print(
            "Legacy directories were left in place. The runtime keeps "
            "reading them; pass --remove-legacy on a follow-up run to "
            "delete the legacy tree once you have verified the copy.",
            file=output,
        )
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tax-pipeline-migrate-buckets",
        description=(
            "Migrate a workspace's raw/ directory from the legacy flat "
            "bucket layout (raw/germany, raw/us, raw/brokers, ...) to "
            "the new Proposal 8 dual-dimension layout "
            "(raw/jurisdictions/<iso>/, raw/asset_classes/<class>/)."
        ),
    )
    parser.add_argument(
        "workspace",
        help=(
            "Path to a workspace directory (e.g. years/demo-2025) "
            "containing a raw/ subdirectory."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the copies (default: dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would change (the default).",
    )
    parser.add_argument(
        "--remove-legacy",
        action="store_true",
        help=(
            "After a successful --apply, delete the legacy flat "
            "directories. Default: leave them in place."
        ),
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    workspace = Path(args.workspace).resolve()
    apply = bool(args.apply) and not bool(args.dry_run)
    if args.remove_legacy and not apply:
        parser.error("--remove-legacy requires --apply")

    migrate_workspace(workspace, apply=apply, remove_legacy=bool(args.remove_legacy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
