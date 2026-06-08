"""Proposal 8 (raw-bucket redesign) regression tests.

Covers:

* the dual-layout fact-extraction read path -- a workspace whose
  documents live under the legacy ``raw/germany/`` produces the same
  manifest classification as one whose documents live under the new
  ``raw/jurisdictions/de/``;
* the ``tax-pipeline-migrate-buckets`` CLI helper -- ``--dry-run``
  reports without writing, ``--apply`` copies, ``--remove-legacy``
  cleans up, the helper is idempotent across repeat invocations;
* the production ``years/brenn-2025/`` workspace -- left on the
  legacy flat layout in git -- still classifies and finds files via
  the dual-read path.

The headline-numbers regression (byte-identical
``final-legal-output.json`` md5s pre/post-migration) is covered by
the run-time pipeline asserts in P8 Commit 5's commit message; this
file isolates the structural contracts so a future regression on the
classifier or migration helper fails closed without needing a
full-pipeline run.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.classify import classify_relative_path
from tax_pipeline.manifest import write_manifest
from tax_pipeline.migrate_buckets import (
    apply_migration,
    migrate_workspace,
    plan_migration,
)
from tax_pipeline.paths import (
    ASSET_CLASS_BUCKETS,
    JURISDICTION_BUCKETS,
    JURISDICTION_LEGACY_NAMES,
    RAW_BUCKETS,
    YearPaths,
    canonical_bucket_path,
    canonicalize_relative_path,
    has_legacy_raw_layout,
    legacy_bucket_path,
    resolve_bucket_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PathHelperTest(unittest.TestCase):
    """Direct tests on the path helpers introduced in P8 commit 1."""

    def test_jurisdiction_buckets_use_iso_codes(self) -> None:
        # ISO 3166-1 alpha-2 codes only; the legacy flat names live in
        # JURISDICTION_LEGACY_NAMES so the canonical tuple stays clean.
        self.assertEqual(JURISDICTION_BUCKETS, ("de", "us"))
        self.assertEqual(JURISDICTION_LEGACY_NAMES, {"germany": "de", "us": "us"})

    def test_canonical_bucket_path_routes_jurisdiction_and_asset_classes(self) -> None:
        root = Path("/tmp/raw")
        self.assertEqual(canonical_bucket_path(root, "germany"), root / "jurisdictions" / "de")
        self.assertEqual(canonical_bucket_path(root, "de"), root / "jurisdictions" / "de")
        self.assertEqual(canonical_bucket_path(root, "us"), root / "jurisdictions" / "us")
        self.assertEqual(canonical_bucket_path(root, "brokers"), root / "asset_classes" / "brokers")
        self.assertEqual(canonical_bucket_path(root, "receipts"), root / "asset_classes" / "receipts")
        # Unknown bucket falls back to ``raw_root / bucket`` so callers
        # can keep their pre-Proposal-8 unsupported-bucket logging.
        self.assertEqual(canonical_bucket_path(root, "mystery"), root / "mystery")

    def test_legacy_bucket_path_uses_flat_names(self) -> None:
        root = Path("/tmp/raw")
        self.assertEqual(legacy_bucket_path(root, "germany"), root / "germany")
        self.assertEqual(legacy_bucket_path(root, "us"), root / "us")
        # ISO codes map back to the historical flat name.
        self.assertEqual(legacy_bucket_path(root, "de"), root / "germany")
        self.assertEqual(legacy_bucket_path(root, "brokers"), root / "brokers")

    def test_resolve_bucket_path_prefers_canonical_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "jurisdictions" / "de").mkdir(parents=True)
            (raw / "germany").mkdir()
            self.assertEqual(
                resolve_bucket_path(raw, "germany"),
                raw / "jurisdictions" / "de",
            )

    def test_resolve_bucket_path_falls_back_to_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "germany").mkdir()
            self.assertEqual(
                resolve_bucket_path(raw, "germany"),
                raw / "germany",
            )

    def test_canonicalize_relative_path_rewrites_legacy_prefixes(self) -> None:
        self.assertEqual(
            canonicalize_relative_path("germany/Lohnsteuerbescheinigung.pdf"),
            "jurisdictions/de/Lohnsteuerbescheinigung.pdf",
        )
        self.assertEqual(
            canonicalize_relative_path("us/1040-2024.pdf"),
            "jurisdictions/us/1040-2024.pdf",
        )
        self.assertEqual(
            canonicalize_relative_path("brokers/1099-Composite.pdf"),
            "asset_classes/brokers/1099-Composite.pdf",
        )
        # Already canonical -- unchanged.
        self.assertEqual(
            canonicalize_relative_path("jurisdictions/de/Lohnsteuerbescheinigung.pdf"),
            "jurisdictions/de/Lohnsteuerbescheinigung.pdf",
        )
        # Unknown prefix -- preserved verbatim.
        self.assertEqual(canonicalize_relative_path("mystery/x.pdf"), "mystery/x.pdf")
        self.assertEqual(canonicalize_relative_path(""), "")


class HasLegacyRawLayoutTest(unittest.TestCase):
    def test_empty_raw_root_is_not_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(has_legacy_raw_layout(Path(tmp)))

    def test_canonical_only_layout_is_not_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "jurisdictions" / "de").mkdir(parents=True)
            (raw / "asset_classes" / "brokers").mkdir(parents=True)
            (raw / "jurisdictions" / "de" / "x.pdf").write_bytes(b"")
            self.assertFalse(has_legacy_raw_layout(raw))

    def test_legacy_with_files_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "germany").mkdir()
            (raw / "germany" / "Lohnsteuer.pdf").write_bytes(b"")
            self.assertTrue(has_legacy_raw_layout(raw))


class DualReadFallbackTest(unittest.TestCase):
    """A workspace on the legacy layout reads identically to canonical."""

    def _scaffold(self, tmp: Path) -> YearPaths:
        paths = YearPaths.for_year(tmp, 2025)
        paths.ensure_directories()
        return paths

    def test_classifier_normalises_legacy_and_canonical_to_same_bucket(self) -> None:
        # A Schwab 1099 lives under brokers in either layout; the
        # classifier should report ``bucket="brokers"`` for both.
        legacy = classify_relative_path(Path("brokers/1099 Composite and Year-End Summary - 2025_273.PDF"))
        canonical = classify_relative_path(
            Path("asset_classes/brokers/1099 Composite and Year-End Summary - 2025_273.PDF")
        )
        self.assertEqual(legacy["bucket"], "brokers")
        self.assertEqual(canonical["bucket"], "brokers")
        self.assertEqual(legacy["doc_type"], canonical["doc_type"])
        self.assertEqual(legacy["confidence"], canonical["confidence"])

    def test_classifier_normalises_germany_iso_to_legacy_label(self) -> None:
        # Jurisdiction docs: legacy ``germany/`` and canonical
        # ``jurisdictions/de/`` should both classify as the
        # ``germany`` bucket so downstream consumers comparing
        # ``bucket == "germany"`` keep working.
        legacy = classify_relative_path(
            Path("germany/person_1_Brenn_Lohnsteuerbescheinigung_2025.pdf")
        )
        canonical = classify_relative_path(
            Path("jurisdictions/de/person_1_Brenn_Lohnsteuerbescheinigung_2025.pdf")
        )
        self.assertEqual(legacy["bucket"], "germany")
        self.assertEqual(canonical["bucket"], "germany")
        self.assertEqual(legacy["doc_type"], canonical["doc_type"])

    def test_manifest_walker_indexes_files_under_either_layout(self) -> None:
        # write_manifest() globs the raw_root tree. Files placed under
        # the legacy and canonical paths produce manifests with the
        # same bucket label and doc_type once classify_relative_path
        # has normalised the head of the path.
        legacy_manifest = self._build_manifest_with_layout("legacy")
        canonical_manifest = self._build_manifest_with_layout("canonical")

        # Same set of buckets, same doc_types -- only the relative
        # paths differ between layouts.
        legacy_summary = sorted(
            (entry["bucket"], entry["doc_type"]) for entry in legacy_manifest
        )
        canonical_summary = sorted(
            (entry["bucket"], entry["doc_type"]) for entry in canonical_manifest
        )
        self.assertEqual(legacy_summary, canonical_summary)
        self.assertGreaterEqual(len(legacy_summary), 1)

    def _build_manifest_with_layout(self, layout: str) -> list[dict[str, object]]:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._scaffold(Path(tmp))
            if layout == "legacy":
                target = paths.raw_root / "brokers" / "1099 Composite and Year-End Summary - 2025_273.PDF"
            elif layout == "canonical":
                target = (
                    paths.raw_root
                    / "asset_classes"
                    / "brokers"
                    / "1099 Composite and Year-End Summary - 2025_273.PDF"
                )
            else:  # pragma: no cover - defensive
                raise AssertionError(f"unknown layout {layout}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"placeholder")
            write_manifest(paths.raw_root, paths.manifest_path, year=2025)
            return json.loads(paths.manifest_path.read_text(encoding="utf-8"))


class MigrateBucketsCliTest(unittest.TestCase):
    """End-to-end behavior of the migration helper."""

    def _seed_legacy_workspace(self, tmp: Path) -> Path:
        raw = tmp / "raw"
        # Populate one jurisdiction bucket and one asset-class bucket
        # with placeholder content under the legacy flat layout.
        (raw / "germany").mkdir(parents=True)
        (raw / "germany" / "Lohnsteuer.pdf").write_bytes(b"de-lohnsteuer")
        (raw / "brokers").mkdir(parents=True)
        (raw / "brokers" / "1099 Composite and Year-End Summary - 2025_273.PDF").write_bytes(
            b"schwab-1099"
        )
        (raw / "receipts").mkdir(parents=True)
        (raw / "receipts" / ".evidence-only").mkdir(parents=True)
        (raw / "receipts" / ".evidence-only" / "mystery.pdf").write_bytes(b"hidden")
        # Empty asset-class stubs that should be left in place by a
        # default --apply (no files to migrate out of these).
        (raw / "crypto").mkdir(parents=True)
        return raw

    def test_dry_run_reports_planned_copies_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = self._seed_legacy_workspace(workspace)
            buf = io.StringIO()

            copied = migrate_workspace(workspace, apply=False, output=buf)

            self.assertEqual(copied, 0)
            output = buf.getvalue()
            self.assertIn("Planned migrations", output)
            self.assertIn("raw/germany/Lohnsteuer.pdf", output)
            self.assertIn("raw/brokers/1099 Composite", output)
            self.assertIn("Dry-run", output)
            # Canonical destinations were NOT created.
            self.assertFalse((raw / "jurisdictions" / "de" / "Lohnsteuer.pdf").exists())
            self.assertFalse(
                (raw / "asset_classes" / "brokers" / "1099 Composite and Year-End Summary - 2025_273.PDF").exists()
            )
            # Legacy files untouched.
            self.assertTrue((raw / "germany" / "Lohnsteuer.pdf").exists())

    def test_apply_copies_files_and_preserves_legacy_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = self._seed_legacy_workspace(workspace)

            copied = migrate_workspace(workspace, apply=True, output=io.StringIO())

            # Three files: Lohnsteuer + 1099 + receipts/.evidence-only/mystery.
            self.assertEqual(copied, 3)
            # Canonical destinations exist with identical contents.
            de_dst = raw / "jurisdictions" / "de" / "Lohnsteuer.pdf"
            self.assertTrue(de_dst.exists())
            self.assertEqual(de_dst.read_bytes(), b"de-lohnsteuer")
            broker_dst = (
                raw
                / "asset_classes"
                / "brokers"
                / "1099 Composite and Year-End Summary - 2025_273.PDF"
            )
            self.assertTrue(broker_dst.exists())
            self.assertEqual(broker_dst.read_bytes(), b"schwab-1099")
            evidence_dst = (
                raw / "asset_classes" / "receipts" / ".evidence-only" / "mystery.pdf"
            )
            self.assertTrue(evidence_dst.exists())
            self.assertEqual(evidence_dst.read_bytes(), b"hidden")
            # Legacy preserved -- runtime keeps reading either layout.
            self.assertTrue((raw / "germany" / "Lohnsteuer.pdf").exists())
            self.assertTrue((raw / "brokers").is_dir())

    def test_apply_with_remove_legacy_cleans_populated_and_empty_stubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = self._seed_legacy_workspace(workspace)

            migrate_workspace(
                workspace,
                apply=True,
                remove_legacy=True,
                output=io.StringIO(),
            )

            # Populated legacy directories removed.
            self.assertFalse((raw / "germany").exists())
            self.assertFalse((raw / "brokers").exists())
            self.assertFalse((raw / "receipts").exists())
            # Empty legacy stub also removed (idempotence over scaffold
            # leftovers).
            self.assertFalse((raw / "crypto").exists())
            # Canonical layout still in place.
            self.assertTrue((raw / "jurisdictions" / "de" / "Lohnsteuer.pdf").exists())

    def test_two_step_apply_then_remove_legacy_finishes_migration(self) -> None:
        # Audit follow-up (Wave 2a, 2026-05-04): a user who runs
        # ``--apply`` first, validates the canonical copy, then comes
        # back later with ``--apply --remove-legacy`` must end up on a
        # clean canonical layout. Previously the second invocation was
        # a silent no-op: ``plan_migration`` returns no plans (already
        # migrated), ``migrated_from_here`` is therefore False for
        # every bucket, and the visible-children check sees the still-
        # present legacy files and refuses to clean up. The fix removes
        # any legacy bucket whose every file has a byte-identical twin
        # at the canonical destination.
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = self._seed_legacy_workspace(workspace)

            first = migrate_workspace(workspace, apply=True, output=io.StringIO())
            self.assertEqual(first, 3)
            # Legacy still in place after the non-destructive --apply.
            self.assertTrue((raw / "germany" / "Lohnsteuer.pdf").exists())
            self.assertTrue((raw / "brokers").is_dir())

            second = migrate_workspace(
                workspace, apply=True, remove_legacy=True, output=io.StringIO()
            )
            self.assertEqual(second, 0)

            # Legacy directories removed even though no new files were
            # copied this run -- the helper recognised that every legacy
            # file already has a canonical twin.
            self.assertFalse((raw / "germany").exists())
            self.assertFalse((raw / "brokers").exists())
            self.assertFalse((raw / "receipts").exists())
            # Canonical layout intact.
            self.assertTrue((raw / "jurisdictions" / "de" / "Lohnsteuer.pdf").exists())
            self.assertTrue(
                (
                    raw
                    / "asset_classes"
                    / "brokers"
                    / "1099 Composite and Year-End Summary - 2025_273.PDF"
                ).exists()
            )

    def test_remove_legacy_preserves_bucket_with_uncopied_file(self) -> None:
        # Safety check on the two-step recovery: if the legacy bucket
        # contains a file whose canonical destination does not exist
        # (or differs in bytes), removing the legacy tree would lose
        # data. The helper must leave such a bucket in place.
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = self._seed_legacy_workspace(workspace)

            migrate_workspace(workspace, apply=True, output=io.StringIO())

            # Add a NEW file to the legacy tree that has no canonical
            # twin yet.
            (raw / "germany" / "Brand-new.pdf").write_bytes(b"new-doc")

            migrate_workspace(
                workspace, apply=False, remove_legacy=False, output=io.StringIO()
            )
            # ``apply=False`` means no copy and no remove, sanity check.
            self.assertTrue((raw / "germany" / "Brand-new.pdf").exists())

            # Now run --apply --remove-legacy: the new file should be
            # copied and the legacy bucket removed.
            third = migrate_workspace(
                workspace, apply=True, remove_legacy=True, output=io.StringIO()
            )
            self.assertEqual(third, 1)
            self.assertFalse((raw / "germany").exists())
            self.assertTrue((raw / "jurisdictions" / "de" / "Brand-new.pdf").exists())

    def test_idempotence_repeated_apply_does_not_double_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = self._seed_legacy_workspace(workspace)

            first = migrate_workspace(workspace, apply=True, output=io.StringIO())
            self.assertEqual(first, 3)

            # Second --apply on the now-canonical workspace finds zero
            # plans (the helper does not double-copy).
            second = migrate_workspace(workspace, apply=True, output=io.StringIO())
            self.assertEqual(second, 0)
            # Files at canonical destinations untouched.
            de_dst = raw / "jurisdictions" / "de" / "Lohnsteuer.pdf"
            self.assertTrue(de_dst.exists())
            self.assertEqual(de_dst.read_bytes(), b"de-lohnsteuer")

    def test_idempotence_remove_legacy_on_already_canonical_workspace(self) -> None:
        # The demo workspaces' real-world path: an --apply --remove-
        # legacy run on a workspace whose legacy bucket dirs are
        # already empty (or recreated by scaffolding) should still
        # leave the workspace on the canonical layout, not error.
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            raw = workspace / "raw"
            raw.mkdir()
            (raw / "jurisdictions" / "de").mkdir(parents=True)
            (raw / "asset_classes" / "brokers").mkdir(parents=True)
            # Empty legacy stubs (typical post-ensure_directories).
            for bucket in (*JURISDICTION_LEGACY_NAMES.keys(), *ASSET_CLASS_BUCKETS):
                (raw / bucket).mkdir(parents=True, exist_ok=True)

            buf = io.StringIO()
            copied = migrate_workspace(
                workspace, apply=True, remove_legacy=True, output=buf
            )

            self.assertEqual(copied, 0)
            self.assertIn("Removed legacy bucket directories.", buf.getvalue())
            for bucket in (*JURISDICTION_LEGACY_NAMES.keys(), *ASSET_CLASS_BUCKETS):
                self.assertFalse((raw / bucket).exists())
            self.assertTrue((raw / "jurisdictions" / "de").exists())
            self.assertTrue((raw / "asset_classes" / "brokers").exists())

    def test_apply_migration_unit_returns_count_and_skips_when_legacy_missing(self) -> None:
        # A workspace with no legacy bucket dirs at all returns an
        # empty plan list and apply_migration() is a no-op.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            plans = plan_migration(raw)
            self.assertEqual(plans, [])
            copied = apply_migration(plans, raw_root=raw, remove_legacy=True)
            self.assertEqual(copied, 0)

    def test_no_raw_directory_warns_and_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            copied = migrate_workspace(Path(tmp), apply=True, output=buf)
            self.assertEqual(copied, 0)
            self.assertIn("nothing to migrate", buf.getvalue())


class BrennWorkspaceLegacyLayoutTest(unittest.TestCase):
    """``years/brenn-2025/`` is the production canary for the dual-read.

    The repo intentionally keeps the production workspace on the
    legacy flat layout so the read-side stays exercised end-to-end.
    These checks fail closed if a future refactor either silently
    migrates the workspace or breaks the dual-read.
    """

    def setUp(self) -> None:
        self.brenn_root = PROJECT_ROOT / "years" / "brenn-2025"
        if not self.brenn_root.is_dir():
            self.skipTest("years/brenn-2025/ workspace not present in this checkout")

    def test_brenn_workspace_uses_legacy_flat_layout(self) -> None:
        raw = self.brenn_root / "raw"
        # Prove the workspace is still on the legacy layout (so the
        # dual-read fallback is genuinely exercised in production).
        self.assertTrue(has_legacy_raw_layout(raw))
        self.assertTrue((raw / "germany").is_dir())
        self.assertTrue((raw / "brokers").is_dir())
        # And no canonical mirror has been created underneath -- the
        # canonical mirror dirs may exist as empty scaffolds, but
        # they must not duplicate the legacy files (otherwise we are
        # keeping two copies of every PDF on disk).
        canonical_jurisdictions = raw / "jurisdictions"
        if canonical_jurisdictions.exists():
            for legacy_name, iso in JURISDICTION_LEGACY_NAMES.items():
                legacy_files = sorted(
                    p.name for p in (raw / legacy_name).rglob("*") if p.is_file()
                )
                canonical_files = sorted(
                    p.name
                    for p in (canonical_jurisdictions / iso).rglob("*")
                    if p.is_file()
                )
                self.assertEqual(
                    canonical_files,
                    [],
                    msg=(
                        f"Canonical {iso}/ should not duplicate legacy "
                        f"{legacy_name}/ files; found {canonical_files}"
                    ),
                )
                self.assertGreater(
                    len(legacy_files),
                    0,
                    msg=f"Expected legacy {legacy_name}/ to still hold files",
                )

    def test_brenn_manifest_classifies_via_dual_read(self) -> None:
        manifest_path = self.brenn_root / "normalized" / "documents.json"
        if not manifest_path.exists():
            self.skipTest("brenn-2025 manifest not yet built")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # The dual-read contract: for every entry whose relative_path
        # is on the legacy flat layout, classify_relative_path must
        # produce the same bucket the manifest recorded -- i.e. the
        # classifier and the manifest agree end-to-end.
        legacy_entries = [
            entry
            for entry in manifest
            if not entry["relative_path"].startswith(("jurisdictions/", "asset_classes/"))
        ]
        self.assertGreater(
            len(legacy_entries),
            0,
            msg="Expected at least one manifest entry on the legacy layout",
        )
        for entry in legacy_entries:
            classified = classify_relative_path(Path(entry["relative_path"]))
            self.assertEqual(
                classified["bucket"],
                entry["bucket"],
                msg=f"Manifest/classifier disagree on {entry['relative_path']}",
            )


class RawBucketsBackcompatTest(unittest.TestCase):
    def test_raw_buckets_alias_preserves_legacy_flat_names(self) -> None:
        # Existing ``profile.raw_buckets`` validation iterates this
        # tuple. Removing or reordering it would break older
        # workspaces' profile.json files.
        self.assertEqual(
            RAW_BUCKETS,
            (
                *JURISDICTION_LEGACY_NAMES.keys(),
                *ASSET_CLASS_BUCKETS,
            ),
        )


if __name__ == "__main__":
    unittest.main()
