from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.fact_extraction import DocumentFacts, extract_all_facts, extract_document_facts_from_pages, write_document_facts
from tax_pipeline.fact_validation import ValidationIssue, document_facts_from_dict, validate_all_facts, validate_document_facts
from tax_pipeline.paths import YearPaths
from tests.y_agnostic.test_fact_extraction import (
    COINBASE_1099_DA_PAGE_2,
    JPM_PAGE_1,
    LOHNSTEUER_GERMAN_PAGE,
    US_1040_PACKET_PAGE_1,
    US_1040_PACKET_REAL_LAYOUT,
    US_8879_PAGE_1,
)


class FactValidationTest(unittest.TestCase):
    def test_valid_docs_pass_validation(self) -> None:
        docs = [
            extract_document_facts_from_pages(
                relative_path=Path("germany/person_2_Lohnsteuerbescheinigung_122025_260410_210646.pdf"),
                doc_type="german_lohnsteuer_pdf",
                pages=[LOHNSTEUER_GERMAN_PAGE],
            ),
            extract_document_facts_from_pages(
                relative_path=Path("equity_comp/JPM-1099Statement.pdf"),
                doc_type="jpm_1099_pdf",
                pages=[JPM_PAGE_1],
            ),
            extract_document_facts_from_pages(
                relative_path=Path("us/1040-2024-Alex-Example-final.pdf"),
                doc_type="us_1040_packet_pdf",
                pages=[US_1040_PACKET_PAGE_1, US_1040_PACKET_REAL_LAYOUT],
            ),
            extract_document_facts_from_pages(
                relative_path=Path("us/8879-2024-Alex-Example-final.pdf"),
                doc_type="us_8879_pdf",
                pages=[US_8879_PAGE_1],
            ),
            extract_document_facts_from_pages(
                relative_path=Path("crypto/coinbase-1099-DA.pdf"),
                doc_type="coinbase_1099_da_pdf",
                pages=["", COINBASE_1099_DA_PAGE_2],
            ),
        ]
        for doc in docs:
            self.assertEqual(validate_document_facts(doc), [], doc.relative_path)

    def test_invalid_relative_values_are_flagged(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/1040-2024-Alex-Example-final.pdf"),
            doc_type="us_1040_packet_pdf",
            pages=[US_1040_PACKET_REAL_LAYOUT],
        )
        payload = doc.to_dict()
        for fact in payload["facts"]:
            if fact["key"] == "form_1040_line_3a_qualified_dividends_usd":
                fact["value"] = "20000.00"
        mutated = document_facts_from_dict(payload)
        issues = validate_document_facts(mutated)
        self.assertTrue(any(issue.rule == "relative_value" for issue in issues))

    def test_non_ok_extraction_status_fails_closed_for_non_evidence_documents(self) -> None:
        doc = DocumentFacts(
            relative_path="brokers/blank-1099.pdf",
            doc_type="schwab_1099_pdf",
            parser="deterministic.pdf_text.v1",
            status="needs_ocr",
            facts=[],
            warnings=["No extractable text found; OCR or manual review required"],
        )

        issues = validate_document_facts(doc)

        self.assertTrue(any(issue.rule == "document_extraction_status" for issue in issues), issues)

    def test_validate_all_facts_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()

            doc = extract_document_facts_from_pages(
                relative_path=Path("equity_comp/JPM-1099Statement.pdf"),
                doc_type="jpm_1099_pdf",
                pages=[JPM_PAGE_1],
            )
            json_path, md_path = write_document_facts(paths, doc)
            index_rows = [
                {
                    "relative_path": doc.relative_path,
                    "doc_type": doc.doc_type,
                    "status": doc.status,
                    "facts_count": len(doc.facts),
                    "json_path": json_path.relative_to(root).as_posix(),
                    "markdown_path": md_path.relative_to(root).as_posix(),
                }
            ]

            issues = validate_all_facts(paths, index_rows)

            self.assertEqual(issues, [])
            validation_payload = json.loads((paths.facts_root / "validation.json").read_text())
            self.assertEqual(validation_payload, [])
            self.assertIn("result: `ok`", (paths.facts_root / "VALIDATION.md").read_text())

    def test_validate_all_facts_resolves_index_paths_relative_to_external_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            workspace = Path(tmp) / "external" / "2026"
            paths = YearPaths.for_workspace(root, workspace, 2026)
            paths.ensure_directories()
            doc = extract_document_facts_from_pages(
                relative_path=Path("equity_comp/JPM-1099Statement.pdf"),
                doc_type="jpm_1099_pdf",
                pages=[JPM_PAGE_1],
            )
            json_path, md_path = write_document_facts(paths, doc)
            index_rows = [
                {
                    "relative_path": doc.relative_path,
                    "doc_type": doc.doc_type,
                    "status": doc.status,
                    "facts_count": len(doc.facts),
                    "json_path": json_path.relative_to(paths.year_root).as_posix(),
                    "markdown_path": md_path.relative_to(paths.year_root).as_posix(),
                }
            ]

            issues = validate_all_facts(paths, index_rows)

            self.assertEqual(issues, [])

    def test_extract_all_facts_fails_closed_when_validation_has_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()

            with (
                mock.patch("tax_pipeline.fact_extraction.load_manifest", return_value=[]),
                mock.patch(
                    "tax_pipeline.fact_extraction.validate_all_facts",
                    return_value=[
                        ValidationIssue(
                            "germany/wage.pdf",
                            "error",
                            "required_field",
                            "gross wage missing",
                        )
                    ],
                ),
            ):
                with self.assertRaisesRegex(ValueError, "Fact validation failed"):
                    extract_all_facts(paths)


if __name__ == "__main__":
    unittest.main()
