from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_german_social_insurance_notice_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    specs = [
        ("notice_date", r"Datum:\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})", "date", "", "Notice date"),
        (
            "created_or_transmitted_at",
            r"Pers\.-Nr\.\s+Erstellungs-/Übermittlungsdatum\s+[0-9]+\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*/\s*[0-9]{2}:[0-9]{2})",
            "text",
            "",
            "Created or transmitted timestamp",
        ),
        ("personnel_number", r"Pers\.-Nr\.\s+([0-9]+)", "text", "", "Personnel number"),
        (
            "insurance_number",
            r"Versicherungsnummer\s+Geburtsdatum\s+([A-Z0-9]+)",
            "text",
            "",
            "Insurance number",
        ),
        (
            "employee_name",
            r"(?m)^\s*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß' -]+)\s*$\n\s*c/o\b",
            "text",
            "",
            "Employee name",
        ),
        ("employer_name", r"^\s*([^\n]+)\*Reichenberger Str\.", "text", "", "Employer name"),
        (
            "submission_reason_code",
            r"Grund der Abgabe\s+([0-9]{2})\s+Abmeldung wegen Ende der Beschäftigung",
            "text",
            "",
            "Submission reason code",
        ),
        (
            "submission_reason_text",
            r"Grund der Abgabe\s+[0-9]{2}\s+([^\n]+)",
            "text",
            "",
            "Submission reason text",
        ),
        (
            "health_insurer_name",
            r"Betriebs-Nr\. Krankenkasse/Einzugsstelle\s+[0-9]+\s+[A-Z]{2}\s+([^\n]+)",
            "text",
            "",
            "Health insurer",
        ),
        ("employer_number", r"Betriebs-Nr\. Arbeitgeber\s+([0-9]+)", "text", "", "Employer number"),
        ("nationality", r"Staatsangehörigkeit\s+[0-9]+\s+([^\n]+)", "text", "", "Nationality"),
    ]

    for key, pattern, value_type, unit, section in specs:
        found = find_first_match(pages, pattern, flags=re.MULTILINE)
        if not found:
            warnings.append(f"Missing pattern for {section}")
            continue
        page, match = found
        facts.append(
            fact(
                key=key,
                value=match.group(1).strip(),
                value_type=value_type,
                unit=unit,
                page=page,
                section=section,
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_social_insurance_notice_pdf",
        "deterministic.german_social_insurance_notice_pdf.v1",
        status,
        facts,
        warnings,
    )
