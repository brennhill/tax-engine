from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from tax_pipeline.providers.shared.provenance import fact, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_schwab_limitation_image(relative_path: Path, pages: list[str]) -> DocumentFacts:
    text = pages[0] if pages else ""
    facts: list[FactRecord] = []
    warnings: list[str] = []

    years_match = re.search(r"Only\s+(\d+)\s+prior years", text, re.IGNORECASE)
    if years_match:
        facts.append(
            fact(
                key="historical_data_window_years",
                value=years_match.group(1),
                value_type="integer",
                unit="years",
                page=1,
                section="Schwab transaction-history limitation notice",
                snippet_text=snippet(text, years_match.start(), years_match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Schwab historical data window")

    date_match = re.search(r"(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/(20\d{2})", text)
    if date_match:
        mm, dd, yyyy = date_match.groups()
        iso_date = datetime.strptime(f"{mm}/{dd}/{yyyy}", "%m/%d/%Y").date().isoformat()
        facts.append(
            fact(
                key="earliest_available_start_date",
                value=iso_date,
                value_type="date",
                unit="",
                page=1,
                section="Schwab earliest available date",
                snippet_text=snippet(text, date_match.start(), date_match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Schwab earliest available date")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "schwab_limitation_image",
        "deterministic.schwab_limitation_image.v1",
        status,
        facts,
        warnings,
    )
