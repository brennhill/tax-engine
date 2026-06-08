from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.german_lohnsteuerbescheinigung import extract_german_lohnsteuerbescheinigung
from tax_pipeline.providers.shared.schema import DocumentFacts


def extract_datev_lohnsteuerbescheinigung_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    return extract_german_lohnsteuerbescheinigung(relative_path, pages)
