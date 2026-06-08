from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.german_verlustvortrag import extract_german_verlustvortrag
from tax_pipeline.providers.shared.schema import DocumentFacts


def extract_finanzamt_verlustvortrag_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    return extract_german_verlustvortrag(relative_path, pages)
