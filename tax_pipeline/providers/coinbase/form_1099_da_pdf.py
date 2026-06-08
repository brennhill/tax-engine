from __future__ import annotations

from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_coinbase_1099_da_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    specs = [
        (
            r"Coinbase\s+Short\s+\$\s*([0-9,]+\.\d{2})\s+\$\s*([0-9,]+\.\d{2})\s+(-?\$\s*[0-9,]+\.\d{2})",
            [
                ("short_term_proceeds_usd", 1, "Coinbase 1099-DA summary short proceeds"),
                ("short_term_cost_basis_usd", 2, "Coinbase 1099-DA summary short cost basis"),
                ("short_term_gain_or_loss_usd", 3, "Coinbase 1099-DA summary short gain or loss"),
            ],
        ),
        (
            r"Coinbase\s+Long\s+\$\s*([0-9,]+\.\d{2})\s+\$\s*([0-9,]+\.\d{2})\s+(-?\$\s*[0-9,]+\.\d{2})",
            [
                ("long_term_proceeds_usd", 1, "Coinbase 1099-DA summary long proceeds"),
                ("long_term_cost_basis_usd", 2, "Coinbase 1099-DA summary long cost basis"),
                ("long_term_gain_or_loss_usd", 3, "Coinbase 1099-DA summary long gain or loss"),
            ],
        ),
        (
            r"Total[^\n]*\$\s*([0-9,]+\.\d{2})\s+\$\s*([0-9,]+\.\d{2})\s+(-?\$\s*[0-9,]+\.\d{2})",
            [
                ("total_proceeds_usd", 1, "Coinbase 1099-DA summary total proceeds"),
                ("total_cost_basis_usd", 2, "Coinbase 1099-DA summary total cost basis"),
                ("total_gain_or_loss_usd", 3, "Coinbase 1099-DA summary total gain or loss"),
            ],
        ),
    ]
    for pattern, fields in specs:
        found = find_first_match(pages, pattern)
        if not found:
            warnings.append(f"Missing pattern for {fields[0][2]}")
            continue
        page, match = found
        shared_snippet = snippet(pages[page - 1], match.start(), match.end())
        for key, group_index, section in fields:
            facts.append(
                fact(
                    key=key,
                    value=fmt_money(parse_us_amount(match.group(group_index))),
                    value_type="decimal",
                    unit="USD",
                    page=page,
                    section=section,
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                )
            )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "coinbase_1099_da_pdf",
        "deterministic.coinbase_1099_da_pdf.v1",
        status,
        facts,
        warnings,
    )
