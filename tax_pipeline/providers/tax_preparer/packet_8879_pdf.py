from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.dates import iso_month_day_year
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_tax_preparer_8879_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    cover_specs = [
        ("prepared_for", r"Prepared for:\s+([^\n]+)", "text", "", "Cover prepared for", lambda raw: raw.strip(" .")),
        (
            "cover_income_tax_payable_usd",
            r"Income tax payable:\s+US\$\s*([0-9,]+)",
            "decimal",
            "USD",
            "Cover income tax payable",
            lambda raw: fmt_money(parse_us_amount(raw)),
        ),
        (
            "late_payment_penalty_interest_usd",
            r"Late payment penalty \+ interest:\s+\$\s*([0-9,]+)",
            "decimal",
            "USD",
            "Cover late payment penalty and interest",
            lambda raw: fmt_money(parse_us_amount(raw)),
        ),
        (
            "cover_total_due_usd",
            r"Total:\s+\$\s*([0-9,]+)",
            "decimal",
            "USD",
            "Cover total due",
            lambda raw: fmt_money(parse_us_amount(raw)),
        ),
        (
            "cover_filing_deadline",
            r"Filing deadline:\s+([A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4})",
            "date",
            "",
            "Cover filing deadline",
            iso_month_day_year,
        ),
    ]

    for key, pattern, value_type, unit, section, transform in cover_specs:
        found = find_first_match(pages, pattern, flags=re.MULTILINE)
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

    signed_by_patterns = [
        r"Signed and dated\s+([^\n]+)\s+by:",
        r"Signed and dated\s+by:\s+([^\n]+)",
    ]
    signed_by_found = None
    for pattern in signed_by_patterns:
        signed_by_found = find_first_match(pages, pattern, flags=re.MULTILINE)
        if signed_by_found:
            break
    if signed_by_found:
        page, match = signed_by_found
        facts.append(
            fact(
                key="signed_by",
                value=match.group(1).strip(),
                value_type="text",
                unit="",
                page=page,
                section="Cover signed by",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Cover signed by")

    form_text = "\n".join(pages)
    form_specs = [
        ("tax_year", r"Tax Year Ending December 31,\s+([0-9]{4})", "integer", "year", "Form 8879 tax year"),
        ("agi_usd", r"\b1\s+Adjusted gross income.*?\b1\s+([0-9,]+)\.", "decimal", "USD", "Form 8879 line 1"),
        ("total_tax_usd", r"\b2\s+Total tax.*?\b2\s+([0-9,]+)\.", "decimal", "USD", "Form 8879 line 2"),
        ("amount_owed_usd", r"Amount you owe.*?([0-9,]+)\.\.?", "decimal", "USD", "Form 8879 line 5"),
    ]
    for key, pattern, value_type, unit, section in form_specs:
        match = re.search(pattern, form_text, re.MULTILINE | re.DOTALL)
        if not match:
            warnings.append(f"Missing pattern for {section}")
            continue
        value = match.group(1)
        if value_type == "decimal":
            value = fmt_money(parse_us_amount(value))
        facts.append(
            fact(
                key=key,
                value=value,
                value_type=value_type,
                unit=unit,
                page=1,
                section=section,
                snippet_text=snippet(form_text, match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "us_8879_pdf",
        "deterministic.us_8879_pdf.v1",
        status,
        facts,
        warnings,
    )
