from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_localized_amount
from tax_pipeline.providers.shared.dates import iso_dash_abbrev_date
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def _summary_total(page_text: str, label: str) -> str | None:
    match = re.search(
        rf"{re.escape(label)}\s+€([0-9\.,]+)\s+€([0-9\.,]+)",
        page_text,
        re.MULTILINE,
    )
    if not match:
        return None
    return match.group(1)


def _count_transaction_rows(page_text: str) -> int:
    count = 0
    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"\d{4}-\d{2}-\d{2}\s+\d{4}-\d{2}-\d{2}$", stripped):
            count += 1
            continue
        if re.search(r"\d{4}-\d{2}-\d{2}$", stripped) and (
            "EUR" in stripped or "Delivery Hero SE" in stripped or "Participant" in stripped
        ):
            count += 1
    return count


def extract_shareworks_statement_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    text = "\n".join(pages)
    facts: list[FactRecord] = []
    warnings: list[str] = []

    if re.search(r"No records found", text, re.IGNORECASE):
        facts.append(
            fact(
                key="report_result",
                value="no_records_found",
                value_type="text",
                unit="",
                page=1,
                section="Shareworks report status",
                snippet_text="No records found",
                relative_path=relative_path.as_posix(),
            )
        )
        return DocumentFacts(
            relative_path.as_posix(),
            "shareworks_statement_pdf",
            "deterministic.shareworks_statement_pdf.v1",
            "ok",
            facts,
            warnings,
        )

    published = find_first_match(pages, r"Published Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
    if published:
        page, match = published
        facts.append(
            fact(
                key="published_date",
                value=match.group(1),
                value_type="date",
                unit="",
                page=page,
                section="Shareworks published date",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    statement_period = find_first_match(
        pages,
        r"Statement Period\s+([0-9]{4}-[0-9]{2}-[0-9]{2})\s+to\s+([0-9]{4}-[0-9]{2}-[0-9]{2})",
    )
    if statement_period:
        page, match = statement_period
        shared_snippet = snippet(pages[page - 1], match.start(), match.end())
        facts.extend(
            [
                fact(
                    key="statement_period_start",
                    value=match.group(1),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Shareworks statement period start",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
                fact(
                    key="statement_period_end",
                    value=match.group(2),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Shareworks statement period end",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )

    summary_period = find_first_match(
        pages,
        r"Summary Period:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})\s+to\s+([0-9]{2}-[A-Za-z]{3}-[0-9]{4})",
    )
    if summary_period:
        page, match = summary_period
        shared_snippet = snippet(pages[page - 1], match.start(), match.end())
        facts.extend(
            [
                fact(
                    key="summary_period_start",
                    value=iso_dash_abbrev_date(match.group(1)),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Shareworks summary period start",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
                fact(
                    key="summary_period_end",
                    value=iso_dash_abbrev_date(match.group(2)),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Shareworks summary period end",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )

    account_number = find_first_match(pages, r"Account Number[:\s]+([A-Z0-9\-]+)")
    if account_number:
        page, match = account_number
        facts.append(
            fact(
                key="account_number",
                value=match.group(1),
                value_type="text",
                unit="",
                page=page,
                section="Shareworks account number",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    company = find_first_match(pages, r"Company:\s*([^\n]+)")
    if company:
        page, match = company
        facts.append(
            fact(
                key="company_name",
                value=match.group(1).strip(),
                value_type="text",
                unit="",
                page=page,
                section="Shareworks company",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    for page_number, page_text in enumerate(pages, start=1):
        total_value = _summary_total(page_text, "Total")
        if total_value is not None:
            match = re.search(r"Total\s+€([0-9\.,]+)\s+€([0-9\.,]+)", page_text, re.MULTILINE)
            shared_snippet = match.group(0) if match else "Total"
            facts.extend(
                [
                    fact(
                        key="summary_total_value_eur",
                        value=fmt_money(parse_localized_amount(total_value)),
                        value_type="decimal",
                        unit="EUR",
                        page=page_number,
                        section="Shareworks account summary total value",
                        snippet_text=shared_snippet,
                        relative_path=relative_path.as_posix(),
                    ),
                    fact(
                        key="summary_available_value_eur",
                        value=fmt_money(parse_localized_amount(match.group(2))) if match else "0.00",
                        value_type="decimal",
                        unit="EUR",
                        page=page_number,
                        section="Shareworks account summary available value",
                        snippet_text=shared_snippet,
                        relative_path=relative_path.as_posix(),
                    ),
                ]
            )
            break

    for page_number, page_text in enumerate(pages, start=1):
        if "Account Transactions" not in page_text:
            continue
        count = _count_transaction_rows(page_text)
        facts.append(
            fact(
                key="transaction_row_count",
                value=str(count),
                value_type="integer",
                unit="rows",
                page=page_number,
                section="Shareworks account transactions",
                snippet_text="Account Transactions",
                relative_path=relative_path.as_posix(),
            )
        )
        break

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "shareworks_statement_pdf",
        "deterministic.shareworks_statement_pdf.v1",
        status,
        facts,
        warnings,
    )
