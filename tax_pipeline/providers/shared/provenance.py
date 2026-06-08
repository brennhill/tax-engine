from __future__ import annotations

import re

from tax_pipeline.providers.shared.schema import FactRecord


def snippet(page_text: str, start: int, end: int, radius: int = 120) -> str:
    text = page_text[max(0, start - radius) : min(len(page_text), end + radius)].strip()
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def find_first_match(
    pages: list[str], pattern: str, flags: int = re.MULTILINE | re.DOTALL
) -> tuple[int, re.Match[str]] | None:
    regex = re.compile(pattern, flags)
    for index, page_text in enumerate(pages, start=1):
        match = regex.search(page_text)
        if match:
            return index, match
    return None


def fact(
    *,
    key: str,
    value: str,
    value_type: str,
    unit: str,
    page: int,
    section: str,
    snippet_text: str,
    relative_path: str,
    confidence: str = "high",
    notes: str = "",
) -> FactRecord:
    return FactRecord(
        key=key,
        value=value,
        value_type=value_type,
        unit=unit,
        confidence=confidence,
        source={
            "file": relative_path,
            "page": page,
            "section": section,
            "snippet": snippet_text,
        },
        notes=notes,
    )
