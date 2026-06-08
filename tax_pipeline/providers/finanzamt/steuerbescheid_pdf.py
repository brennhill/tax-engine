from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.german_steuerbescheid import extract_german_steuerbescheid
from tax_pipeline.providers.shared.schema import DocumentFacts


def extract_finanzamt_steuerbescheid_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    return extract_german_steuerbescheid(relative_path, pages)
