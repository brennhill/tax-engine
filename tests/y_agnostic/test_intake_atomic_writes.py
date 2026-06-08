"""F-A5 — Atomic write contract for intake persistence.

The four intake modules (``postures``, ``screens``, ``uploads``,
``workspace``) all persist user state through ``Path.write_text`` and
``csv.DictWriter`` against a non-temp target. Without invariant I9
(unique temp filename + parent fsync) any of these can leave a torn
or empty file on disk if a crash, OS kill, or concurrent writer
intervenes mid-write — and the next screen-restore read would then
see corrupted state.

This test mirrors the contract enforced by
``tests/test_final_legal_output_atomic.py`` for the legal-output
triple, applied to the intake writers:

  * Force ``os.replace`` to raise during the write — the original
    file content (or absence thereof) must be preserved.
  * After a successful write, no ``.tmp`` siblings remain in the
    parent directory.

Authority context: invariant I9 is the structural guard rail that
caught H9 (atomic-write filename collision); the same posture applies
here because intake state can be partial-saved while another process
is reading it (the wizard auto-saves while the form is mounted and
the engine inputs read the same files).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tax_pipeline.intake import postures as postures_module
from tax_pipeline.intake.postures import write_posture_state
from tax_pipeline.intake.screens import write_identity_state
from tax_pipeline.intake.uploads import store_upload
from tax_pipeline.intake.workspace import write_household
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _make_workspace(tmpdir: Path) -> object:
    workspace_root = tmpdir / "2026"
    paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
    ensure_year_scaffold(paths)
    return paths


def _no_temp_files(parent: Path) -> list[str]:
    """Return any ``.<name>.<...>.tmp`` siblings remaining in ``parent``."""
    return sorted(
        p.name
        for p in parent.glob(".*.tmp")
        if p.is_file()
    )


class PosturesAtomicWriteTest(unittest.TestCase):
    def test_partial_failure_preserves_prior_profile_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))

            # Establish a known-good baseline.
            baseline = {field.key: field.default for field in postures_module.POSTURE_REGISTRY}
            write_posture_state(paths, baseline)
            prior_text = paths.profile_path.read_text(encoding="utf-8")
            self.assertTrue(prior_text)

            # Force os.replace to raise during the next write. The
            # atomic-write contract is that the prior file must stay
            # intact (the failed writer only leaves an orphaned temp,
            # which it then unlinks in its except clause).
            mutated = dict(baseline)
            mutated["elections.use_treaty_resourcing"] = True
            with mock.patch(
                "tax_pipeline.intake.postures.atomic_write_text",
                side_effect=RuntimeError("simulated mid-write failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    write_posture_state(paths, mutated)

            # File on disk is byte-for-byte the prior content.
            self.assertEqual(paths.profile_path.read_text(encoding="utf-8"), prior_text)

    def test_no_temp_files_remain_after_successful_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))
            baseline = {field.key: field.default for field in postures_module.POSTURE_REGISTRY}
            write_posture_state(paths, baseline)

            self.assertEqual(_no_temp_files(paths.profile_path.parent), [])
            # elections.csv parent
            self.assertEqual(_no_temp_files(paths.elections_path.parent), [])


class ScreensAtomicWriteTest(unittest.TestCase):
    def test_partial_failure_preserves_prior_profile_and_people(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))

            # Establish a baseline with a single identity row.
            baseline_payload = {
                "household": {
                    "marital_status_on_dec_31": "single",
                    "germany_filing_posture": "single",
                    "usa_filing_posture": "single",
                },
                "people": [
                    {
                        "person_id": "p1",
                        "display_name": "Test User",
                        "first_name": "Test",
                        "last_name": "User",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "country_of_tax_residence": "DE",
                        "german_tax_id": "12345678901",
                    }
                ],
                "payments": [],
            }
            write_household(paths, baseline_payload)
            prior_profile = paths.profile_path.read_text(encoding="utf-8")
            prior_people = paths.people_path.read_text(encoding="utf-8")

            # Force the next screens write to fail. screens.write_identity_state
            # writes to profile.json + people.csv via _write_json/_write_csv,
            # both of which now route through atomic_write_text.
            with mock.patch(
                "tax_pipeline.intake.screens.atomic_write_text",
                side_effect=RuntimeError("simulated mid-write failure"),
            ):
                with self.assertRaises(RuntimeError):
                    write_identity_state(
                        paths,
                        {
                            "household": {
                                "marital_status_on_dec_31": "single",
                            },
                            "people": [
                                {
                                    "person_id": "p1",
                                    "display_name": "Mutated User",
                                    "first_name": "Mutated",
                                    "last_name": "User",
                                }
                            ],
                        },
                    )

            self.assertEqual(paths.profile_path.read_text(encoding="utf-8"), prior_profile)
            self.assertEqual(paths.people_path.read_text(encoding="utf-8"), prior_people)

    def test_no_temp_files_after_screens_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))
            payload = {
                "household": {
                    "marital_status_on_dec_31": "single",
                },
                "people": [
                    {
                        "person_id": "p1",
                        "display_name": "Test User",
                        "first_name": "Test",
                        "last_name": "User",
                    }
                ],
            }
            write_identity_state(paths, payload)
            self.assertEqual(_no_temp_files(paths.profile_path.parent), [])
            self.assertEqual(_no_temp_files(paths.people_path.parent), [])


class UploadsAtomicWriteTest(unittest.TestCase):
    def test_partial_failure_preserves_prior_upload_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))

            # Establish a baseline upload index with one entry.
            store_upload(paths, "Lohnsteuerbescheinigung-2025.pdf", b"%PDF-1.0\nfake\n")
            index_path = paths.raw_root / ".intake-uploads.json"
            self.assertTrue(index_path.exists())
            prior_index = index_path.read_text(encoding="utf-8")
            prior_entries = json.loads(prior_index)
            self.assertEqual(len(prior_entries), 1)

            # Force the next index write to raise. The original index
            # must remain byte-for-byte intact.
            with mock.patch(
                "tax_pipeline.intake.uploads.atomic_write_text",
                side_effect=RuntimeError("simulated mid-write failure"),
            ):
                with self.assertRaises(RuntimeError):
                    store_upload(paths, "verlustvortrag-2025.pdf", b"%PDF-1.0\nfake2\n")

            self.assertEqual(index_path.read_text(encoding="utf-8"), prior_index)

    def test_no_temp_files_after_uploads_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))
            store_upload(paths, "Lohnsteuerbescheinigung-2025.pdf", b"%PDF-1.0\nfake\n")
            self.assertEqual(_no_temp_files(paths.raw_root), [])


class WorkspaceAtomicWriteTest(unittest.TestCase):
    def test_partial_failure_preserves_prior_people_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))

            baseline = {
                "household": {
                    "marital_status_on_dec_31": "single",
                    "germany_filing_posture": "single",
                    "usa_filing_posture": "single",
                },
                "people": [
                    {
                        "person_id": "p1",
                        "display_name": "Test User",
                        "first_name": "Test",
                        "last_name": "User",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "country_of_tax_residence": "DE",
                    }
                ],
                "payments": [],
            }
            write_household(paths, baseline)
            prior_people = paths.people_path.read_text(encoding="utf-8")

            with mock.patch(
                "tax_pipeline.intake.workspace.atomic_write_text",
                side_effect=RuntimeError("simulated mid-write failure"),
            ):
                with self.assertRaises(RuntimeError):
                    write_household(
                        paths,
                        {
                            "household": {
                                "marital_status_on_dec_31": "single",
                                "germany_filing_posture": "single",
                                "usa_filing_posture": "single",
                            },
                            "people": [
                                {
                                    "person_id": "p1",
                                    "display_name": "Mutated User",
                                    "first_name": "Mutated",
                                    "last_name": "User",
                                    "us_filer": True,
                                    "is_taxpayer": True,
                                    "is_spouse": False,
                                    "country_of_tax_residence": "DE",
                                }
                            ],
                            "payments": [],
                        },
                    )

            self.assertEqual(paths.people_path.read_text(encoding="utf-8"), prior_people)

    def test_no_temp_files_after_workspace_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_workspace(Path(tmp))
            payload = {
                "household": {
                    "marital_status_on_dec_31": "single",
                    "germany_filing_posture": "single",
                    "usa_filing_posture": "single",
                },
                "people": [
                    {
                        "person_id": "p1",
                        "display_name": "Test User",
                        "first_name": "Test",
                        "last_name": "User",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "country_of_tax_residence": "DE",
                    }
                ],
                "payments": [],
            }
            write_household(paths, payload)
            self.assertEqual(_no_temp_files(paths.people_path.parent), [])
            self.assertEqual(_no_temp_files(paths.elections_path.parent), [])


if __name__ == "__main__":
    unittest.main()
