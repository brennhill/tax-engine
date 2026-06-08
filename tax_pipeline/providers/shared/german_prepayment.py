from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_german_decimal_comma_amount
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_german_prepayment(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    amount = find_first_match(pages, r"Instant bank transfer\s+([0-9\.\,]+)\s+EUR")
    if amount:
        page, match = amount
        facts.append(
            fact(
                key="payment_amount_eur",
                value=fmt_money(parse_german_decimal_comma_amount(match.group(1))),
                value_type="decimal",
                unit="EUR",
                page=page,
                section="Transfer amount",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for transfer amount")

    value_booking = find_first_match(
        pages,
        r"Value Date\s+Booking Date\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
    )
    if value_booking:
        page, match = value_booking
        shared_snippet = snippet(pages[page - 1], match.start(), match.end())
        facts.extend(
            [
                fact(
                    key="value_date",
                    value=match.group(1),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Transfer value date",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
                fact(
                    key="booking_date",
                    value=match.group(2),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Transfer booking date",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )
    else:
        warnings.append("Missing pattern for transfer dates")

    reference = find_first_match(pages, r"Reference text\s+([^\n]+)")
    if reference:
        page, match = reference
        facts.append(
            fact(
                key="reference_text",
                value=match.group(1).strip(),
                value_type="text",
                unit="",
                page=page,
                section="Transfer reference text",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for transfer reference text")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_prepayment_pdf",
        "deterministic.german_prepayment_pdf.v1",
        status,
        facts,
        warnings,
    )
