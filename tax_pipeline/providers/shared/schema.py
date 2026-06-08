from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FactRecord:
    key: str
    value: str
    value_type: str
    unit: str
    confidence: str
    source: dict[str, object]
    notes: str


@dataclass(frozen=True)
class DocumentFacts:
    relative_path: str
    doc_type: str
    parser: str
    status: str
    facts: list[FactRecord]
    warnings: list[str]
    provider: str | None = None
    document_family: str | None = None
    country_of_origin: str | None = None
    owner: str | None = None
    tax_year: int | None = None
    parser_name: str | None = None
    parser_version: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "doc_type": self.doc_type,
            "parser": self.parser,
            "provider": self.provider,
            "document_family": self.document_family,
            "country_of_origin": self.country_of_origin,
            "owner": self.owner,
            "tax_year": self.tax_year,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "status": self.status,
            "facts": [asdict(fact) for fact in self.facts],
            "warnings": self.warnings,
        }
