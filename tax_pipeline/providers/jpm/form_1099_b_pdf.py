from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.provenance import fact, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_jpm_1099_b_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []
    if not pages:
        return DocumentFacts(
            relative_path.as_posix(),
            "jpm_1099_pdf",
            "deterministic.jpm_1099_pdf.v1",
            "no_text_extracted",
            [],
            ["No pages available"],
        )

    page_text = pages[0]

    text_specs = [
        ("account_number", r"Tax Information for Account\s+([A-Z0-9\-]+)", "JPM 1099 heading", "text", ""),
        (
            "statement_date",
            r"Statement Date(?:\s+[0-9]{4})?.*?([0-9]{2}-[A-Za-z]{3}-[0-9]{4})",
            "JPM statement date",
            "date",
            "",
        ),
    ]
    for key, pattern, section, value_type, unit in text_specs:
        match = re.search(pattern, page_text, re.MULTILINE | re.DOTALL)
        if not match:
            warnings.append(f"Missing pattern for {section}")
            continue
        facts.append(
            fact(
                key=key,
                value=match.group(1),
                value_type=value_type,
                unit=unit,
                page=1,
                section=section,
                snippet_text=snippet(page_text, match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    summary_row = re.search(
        r"Short\s+A \(basis reported to the IRS\).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2})",
        page_text,
        re.MULTILINE | re.DOTALL,
    )
    if summary_row:
        shared_snippet = snippet(page_text, summary_row.start(), summary_row.end())
        proceeds, basis, market_discount, wash_sale, net_gain = summary_row.groups()
        specs = [
            ("short_term_type_a_proceeds_usd", proceeds, "JPM 1099-B short-term proceeds"),
            ("short_term_type_a_cost_basis_usd", basis, "JPM 1099-B short-term cost basis"),
            ("short_term_type_a_market_discount_usd", market_discount, "JPM 1099-B short-term market discount"),
            ("short_term_type_a_wash_sale_loss_disallowed_usd", wash_sale, "JPM 1099-B short-term wash sale disallowed"),
            ("short_term_type_a_net_gain_usd", net_gain, "JPM 1099-B short-term net gain"),
        ]
        for key, raw_amount, section in specs:
            facts.append(
                fact(
                    key=key,
                    value=fmt_money(parse_us_amount(raw_amount)),
                    value_type="decimal",
                    unit="USD",
                    page=1,
                    section=section,
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                )
            )
    else:
        base_start = re.search(r"Short\s+A \(basis reported to the IRS\)", page_text, re.MULTILINE | re.DOTALL)
        if base_start:
            section_text = page_text[base_start.start() :]
            label_specs = [
                ("short_term_type_a_proceeds_usd", r"Proceeds\s+([0-9,]+\.\d{2})", "JPM 1099-B short-term proceeds"),
                ("short_term_type_a_cost_basis_usd", r"Cost basis\s+([0-9,]+\.\d{2})", "JPM 1099-B short-term cost basis"),
                ("short_term_type_a_net_gain_usd", r"Net gain or loss\(-\)\s+([0-9,]+\.\d{2})", "JPM 1099-B short-term net gain"),
            ]
            for key, pattern, section in label_specs:
                match = re.search(pattern, section_text, re.MULTILINE | re.DOTALL)
                if not match:
                    warnings.append(f"Missing pattern for {section}")
                    continue
                facts.append(
                    fact(
                        key=key,
                        value=fmt_money(parse_us_amount(match.group(1))),
                        value_type="decimal",
                        unit="USD",
                        page=1,
                        section=section,
                        snippet_text=snippet(section_text, match.start(), match.end()),
                        relative_path=relative_path.as_posix(),
                    )
                )
            for key, section in [
                ("short_term_type_a_market_discount_usd", "JPM 1099-B short-term market discount"),
                ("short_term_type_a_wash_sale_loss_disallowed_usd", "JPM 1099-B short-term wash sale disallowed"),
            ]:
                facts.append(
                    fact(
                        key=key,
                        value="0.00",
                        value_type="decimal",
                        unit="USD",
                        page=1,
                        section=section,
                        snippet_text=snippet(section_text, 0, min(len(section_text), 200)),
                        relative_path=relative_path.as_posix(),
                        notes="Field absent in fallback summary; interpreted as zero",
                    )
                )
        else:
            warnings.append("Missing short-term Type A summary row")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "jpm_1099_pdf",
        "deterministic.jpm_1099_pdf.v1",
        status,
        facts,
        warnings,
    )
