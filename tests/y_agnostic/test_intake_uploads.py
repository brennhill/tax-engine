from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.intake.uploads import list_uploads, store_upload
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class IntakeUploadsTest(unittest.TestCase):
    def test_supported_upload_is_persisted_in_the_correct_raw_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=Path(tmp) / "2026")
            ensure_year_scaffold(paths)

            result = store_upload(
                paths,
                "1099 Composite and Year-End Summary - 2025_273.PDF",
                b"pdf placeholder",
            )

            self.assertEqual(result["status"], "supported")
            self.assertEqual(result["bucket"], "brokers")
            self.assertEqual(result["doc_type"], "schwab_1099_pdf")
            # Proposal 8: a freshly scaffolded workspace stores uploads
            # under the new canonical layout
            # (``raw/asset_classes/<class>/...``). The legacy flat path
            # is retained as readable but unused.
            self.assertTrue(
                (
                    paths.raw_root
                    / "asset_classes"
                    / "brokers"
                    / "1099 Composite and Year-End Summary - 2025_273.PDF"
                ).exists()
            )

    def test_unsupported_upload_is_marked_unsupported_without_silent_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=Path(tmp) / "2026")
            ensure_year_scaffold(paths)

            result = store_upload(paths, "mystery-document.pdf", b"unknown")

            self.assertEqual(result["status"], "unsupported")
            self.assertFalse(result["stored"])
            self.assertEqual(list(paths.raw_root.rglob("mystery-document.pdf")), [])

    def test_manual_override_can_store_unsupported_upload_as_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=Path(tmp) / "2026")
            ensure_year_scaffold(paths)

            result = store_upload(
                paths,
                "mystery-document.pdf",
                b"unknown",
                manual_bucket="receipts",
                evidence_only=True,
            )

            self.assertEqual(result["status"], "evidence_only")
            self.assertEqual(result["bucket"], "receipts")
            self.assertTrue(result["stored"])
            # Proposal 8: canonical layout stores under
            # ``raw/asset_classes/receipts/.evidence-only/...``.
            self.assertTrue(
                (
                    paths.raw_root
                    / "asset_classes"
                    / "receipts"
                    / ".evidence-only"
                    / "mystery-document.pdf"
                ).exists()
            )

    def test_upload_rejects_filename_path_traversal_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=Path(tmp) / "2026")
            ensure_year_scaffold(paths)

            for filename in ("../evil.pdf", "/tmp/evil.pdf", r"..\\evil.pdf"):
                with self.subTest(filename=filename):
                    with self.assertRaisesRegex(ValueError, "Unsafe upload filename"):
                        store_upload(
                            paths,
                            filename,
                            b"pdf placeholder",
                            manual_bucket="receipts",
                            evidence_only=True,
                        )

            self.assertEqual(list(Path(tmp).rglob("evil.pdf")), [])

    def test_upload_routes_round_trip_saved_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/uploads",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "filename": "1099 Composite and Year-End Summary - 2025_273.PDF",
                    "content_base64": base64.b64encode(b"pdf placeholder").decode("ascii"),
                },
            )

            self.assertEqual(status, 201)
            self.assertEqual(payload["status"], "supported")

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/uploads?year=2026&workspace={workspace_root}",
            )

            self.assertEqual(status, 200)
            self.assertEqual(len(payload["uploads"]), 1)
            self.assertEqual(payload["uploads"][0]["doc_type"], "schwab_1099_pdf")
            self.assertEqual(list_uploads(paths)["uploads"][0]["bucket"], "brokers")


if __name__ == "__main__":
    unittest.main()
