from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_german_decimal_comma_amount
from tax_pipeline.providers.shared.dates import normalize_date
from tax_pipeline.providers.shared.provenance import fact, find_first_match, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_german_steuerbescheid(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    date_match = find_first_match(pages, r"([0-9]{2}\.[0-9]{2}\.[0-9]{4})")
    if date_match:
        page, match = date_match
        facts.append(
            fact(
                key="assessment_date",
                value=normalize_date(match.group(1)),
                value_type="date",
                unit="",
                page=page,
                section="Steuerbescheid heading date",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    dual_specs = [
        (
            "Festgesetzt werden",
            "assessed_income_tax_eur",
            "assessed_solidarity_surcharge_eur",
            "Steuerbescheid assessed tax",
        ),
        (
            "ab Steuerabzug vom Lohn",
            "withheld_income_tax_credit_eur",
            "withheld_solidarity_credit_eur",
            "Steuerbescheid wage tax credits",
        ),
        (
            "verbleibende Steuer",
            "residual_income_tax_eur",
            "residual_solidarity_surcharge_eur",
            "Steuerbescheid residual tax",
        ),
    ]
    for label, left_key, right_key, section in dual_specs:
        found = find_first_match(pages, rf"{re.escape(label)}\s+([0-9\.\,]+)\s+([0-9\.\,]+)")
        if not found:
            warnings.append(f"Missing pattern for {section}")
            continue
        page, match = found
        shared_snippet = snippet(pages[page - 1], match.start(), match.end())
        left_value, right_value = match.groups()
        facts.extend(
            [
                fact(
                    key=left_key,
                    value=fmt_money(parse_german_decimal_comma_amount(left_value)),
                    value_type="decimal",
                    unit="EUR",
                    page=page,
                    section=f"{section} income tax",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
                fact(
                    key=right_key,
                    value=fmt_money(parse_german_decimal_comma_amount(right_value)),
                    value_type="decimal",
                    unit="EUR",
                    page=page,
                    section=f"{section} solidarity surcharge",
                    snippet_text=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )

    due_date = find_first_match(pages, r"spätestens am\s+([0-9]{2}\s*\.[0-9]{2}\.[0-9]{4})")
    if due_date:
        page, match = due_date
        facts.append(
            fact(
                key="payment_due_date",
                value=normalize_date(match.group(1)),
                value_type="date",
                unit="",
                page=page,
                section="Steuerbescheid payment due date",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Steuerbescheid payment due date")

    amount_due = find_first_match(pages, r"Den Gesamtbetrag von\s+([0-9\.\,]+)\s+€")
    if amount_due:
        page, match = amount_due
        facts.append(
            fact(
                key="amount_due_total_eur",
                value=fmt_money(parse_german_decimal_comma_amount(match.group(1))),
                value_type="decimal",
                unit="EUR",
                page=page,
                section="Steuerbescheid total amount due",
                snippet_text=snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Steuerbescheid total amount due")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_steuerbescheid_pdf",
        "deterministic.german_steuerbescheid_pdf.v1",
        status,
        facts,
        warnings,
    )
