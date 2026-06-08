from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.dates import iso_month_day_year
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_tax_preparer_1040_packet_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
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

    full_text = "\n".join(pages)
    form_specs = [
        (
            "mfs_spouse_name",
            r"qualifying person is a child but not your dependent:\s+([^\n]+)",
            "text",
            "",
            "Form 1040 MFS prompt spouse name",
        ),
        (
            "form_1040_line_1h_other_earned_income_usd",
            r"^\s*(?:1h|h)\s+Other earned income.*?\b1h\s+([0-9,]+\.)",
            "decimal",
            "USD",
            "Form 1040 line 1h",
        ),
        (
            "form_1040_line_1z_total_income_usd",
            r"^\s*(?:1z|z)\s+Add lines 1a through 1h.*?\b1z\s+([0-9,]+\.)",
            "decimal",
            "USD",
            "Form 1040 line 1z",
        ),
        ("form_1040_line_2b_taxable_interest_usd", r"\b2b\s+([0-9,]+\.)", "decimal", "USD", "Form 1040 line 2b"),
        ("form_1040_line_3a_qualified_dividends_usd", r"\b3a\s+([0-9,]+\.)", "decimal", "USD", "Form 1040 line 3a"),
        ("form_1040_line_3b_ordinary_dividends_usd", r"\b3b\s+([0-9,]+\.)", "decimal", "USD", "Form 1040 line 3b"),
    ]
    for key, pattern, value_type, unit, section in form_specs:
        match = re.search(pattern, full_text, re.MULTILINE | re.DOTALL)
        if not match:
            warnings.append(f"Missing pattern for {section}")
            continue
        value = match.group(1).strip()
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
                snippet_text=snippet(full_text, match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "us_1040_packet_pdf",
        "deterministic.us_1040_packet_pdf.v1",
        status,
        facts,
        warnings,
    )
