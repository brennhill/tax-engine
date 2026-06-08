from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.provenance import fact, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_schwab_1099_composite_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    specs = [
        ("ordinary_dividends_box_1a_usd", 3, r"1a\s+Total Ordinary Dividends.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 1a"),
        ("qualified_dividends_box_1b_usd", 3, r"1b\s+Qualified Dividends.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 1b"),
        ("capital_gain_distributions_box_2a_usd", 3, r"2a\s+Total Capital Gain Distributions.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 2a"),
        ("nondividend_distributions_box_3_usd", 3, r"3\s+Nondividend Distributions.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 3"),
        ("foreign_tax_paid_box_7_usd", 3, r"7\s+Foreign Tax Paid.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 7"),
        ("interest_income_box_1_usd", 5, r"1\s+Interest Income.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-INT box 1"),
        ("substitute_payments_box_8_usd", 7, r"8\s+Substitute Payments in Lieu of Dividends or Interest.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-MISC box 8"),
        ("foreign_source_income_summary_usd", 90, r"Total Foreign Tax Paid and Income.*?\(?[0-9,]+\.\d{2}\)?\s*\$?\s*([0-9,]+\.\d{2})", "Foreign Tax Paid and Income Summary"),
    ]
    for key, page_number, pattern, section in specs:
        if len(pages) < page_number:
            warnings.append(f"Missing page {page_number} for {section}")
            continue
        page_text = pages[page_number - 1]
        match = re.search(pattern, page_text, re.MULTILINE | re.DOTALL)
        if not match:
            warnings.append(f"Missing pattern for {section}")
            continue
        facts.append(
            fact(
                key=key,
                value=fmt_money(parse_us_amount(match.group(1))),
                value_type="decimal",
                unit="USD",
                page=page_number,
                section=section,
                snippet_text=snippet(page_text, match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "schwab_1099_pdf",
        "deterministic.schwab_1099_pdf.v1",
        status,
        facts,
        warnings,
    )
