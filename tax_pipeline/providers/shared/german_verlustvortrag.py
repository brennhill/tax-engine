from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_decimal, parse_german_standard_amount
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_german_verlustvortrag(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    as_of = find_first_match(pages, r"auf\s+den\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})")
    if as_of:
        page, match = as_of
        facts.append(
            fact(
                key="loss_carryforward_as_of",
                value=match.group(1),
                value_type="date",
                unit="",
                page=page,
                section="Bescheid heading",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    specs = [
        (
            "loss_carryforward_stock_sales_eur",
            r"Kapitalvermögen \(Veräußerung von Aktien\) auf\s+([0-9\.]+)",
            "§ 10d carryforward stock sales",
        ),
        (
            "loss_carryforward_private_sales_eur",
            r"privaten Veräußerungsgeschäften auf\s+([0-9\.]+)",
            "§ 23 carryforward private sales",
        ),
    ]
    for key, pattern, section in specs:
        found = find_first_match(pages, pattern)
        if not found:
            warnings.append(f"Missing pattern for {section}")
            continue
        page, match = found
        facts.append(
            fact(
                key=key,
                value=fmt_decimal(parse_german_standard_amount(match.group(1))),
                value_type="decimal",
                unit="EUR",
                page=page,
                section=section,
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_verlustvortrag_pdf",
        "deterministic.german_verlustvortrag_pdf.v1",
        status,
        facts,
        warnings,
    )
