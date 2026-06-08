from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.german_prepayment import extract_german_prepayment
from tax_pipeline.providers.shared.schema import DocumentFacts


def extract_finanzamt_prepayment_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    return extract_german_prepayment(relative_path, pages)
