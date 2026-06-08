from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentDescriptor:
    provider: str
    document_family: str
    format: str
    doc_type: str
    owner: str | None
    tax_year: int | None
    country_of_origin: str | None
    confidence: str


def descriptor_from_classification(meta: dict[str, object]) -> DocumentDescriptor:
    return DocumentDescriptor(
        provider=str(meta.get("provider") or "unknown"),
        document_family=str(meta.get("document_family") or "unknown"),
        format=str(meta.get("format") or "unknown"),
        doc_type=str(meta["doc_type"]),
        owner=str(meta["owner"]) if meta.get("owner") is not None else None,
        tax_year=int(meta["tax_year"]) if meta.get("tax_year") is not None else None,
        country_of_origin=str(meta["country_of_origin"]) if meta.get("country_of_origin") is not None else None,
        confidence=str(meta["confidence"]),
    )
