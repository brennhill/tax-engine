from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_german_decimal_comma_amount
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_n26_transfer_confirmation_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    specs = [
        (
            "transfer_type",
            r"Transfer Type\s+Amount\s+([A-Za-z ]+?)\s+[0-9\.\,]+\s+EUR",
            "text",
            "",
            "Transfer type",
            lambda raw: raw.strip(),
        ),
        (
            "amount_eur",
            r"Instant bank transfer\s+([0-9\.\,]+)\s+EUR",
            "decimal",
            "EUR",
            "Transfer amount",
            lambda raw: fmt_money(parse_german_decimal_comma_amount(raw)),
        ),
        (
            "transaction_id",
            r"Transaction ID\s+Fee\s+([A-Za-z0-9\-]+)",
            "text",
            "",
            "Transaction identifier",
            lambda raw: raw.strip(),
        ),
        (
            "fee_eur",
            r"Transaction ID\s+Fee\s+[A-Za-z0-9\-]+\s+([0-9\.\,]+)\s+EUR",
            "decimal",
            "EUR",
            "Transfer fee",
            lambda raw: fmt_money(parse_german_decimal_comma_amount(raw)),
        ),
        (
            "reference_text",
            r"Reference text\s+([^\n]+)",
            "text",
            "",
            "Transfer reference text",
            lambda raw: raw.strip(),
        ),
        (
            "sender_name",
            r"SENDER DETAILS\s+([^\n]+)",
            "text",
            "",
            "Sender details",
            lambda raw: raw.strip(),
        ),
        (
            "recipient_name",
            r"RECIPIENT DETAILS\s+([^\n]+)",
            "text",
            "",
            "Recipient details",
            lambda raw: raw.strip(),
        ),
        (
            "issued_on",
            r"Issued on\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
            "date",
            "",
            "Statement issue date",
            lambda raw: raw.strip(),
        ),
    ]

    for key, pattern, value_type, unit, section, transform in specs:
        found = find_first_match(pages, pattern)
        if not found:
            warnings.append(f"Missing pattern for {section}")
            continue
        page, match = found
        facts.append(
            fact(
                key=key,
                value=transform(match.group(1)),
                value_type=value_type,
                unit=unit,
                page=page,
                section=section,
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

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

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "n26_transfer_confirmation_pdf",
        "deterministic.n26_transfer_confirmation_pdf.v1",
        status,
        facts,
        warnings,
    )
